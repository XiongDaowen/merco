"""Agent 主循环与核心逻辑"""

import json
import re
import asyncio
import logging
import shutil
from typing import Optional
from abc import ABC, abstractmethod
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from .config import OpenMercuryConfig
from .llm import LLMClient
from .session import Session
from .message import Message, MessageRole
from .context import ContextManager
from .pipeline import ProcessContext

console = Console()
logger = logging.getLogger("openmercury.agent")

# ── System Prompt 构建器 ─────────────────────────────

class PromptChunk:
    name: str = ""
    def enabled(self, agent) -> bool: return True
    def build(self, agent) -> str: raise NotImplementedError

class PromptBuilder:
    def __init__(self):
        self._chunks: list[PromptChunk] = []
        self._disabled: set[str] = set()
    def use(self, chunk: PromptChunk) -> "PromptBuilder":
        self._chunks.append(chunk); return self
    def disable(self, name: str) -> None: self._disabled.add(name)
    def enable(self, name: str) -> None: self._disabled.discard(name)
    def build(self, agent) -> str:
        return "\n\n".join(c.build(agent) for c in self._chunks
                          if c.name not in self._disabled and c.enabled(agent))

class BasePromptChunk(PromptChunk):
    name = "base"
    PROMPT = """You are OpenMercury, an AI coding assistant. You can help with:
- Writing and editing code
- Answering questions about the codebase
- Executing shell commands
- Searching and managing files

When you need to perform actions, use the available tools.
Always be concise and helpful."""
    def build(self, agent) -> str: return self.PROMPT

class SkillsHintChunk(PromptChunk):
    name = "skills_hint"
    def enabled(self, agent) -> bool:
        return bool(agent.skill_registry and agent.skill_registry.list_skills())
    def build(self, agent) -> str:
        return "使用 skill_view 工具可以加载项目相关的技能说明文档。"


class ResponseProvider(ABC):
    """响应策略基类 — 工厂模式，Agent 不感知流/非流"""

    @abstractmethod
    async def get_response(self, agent: "Agent", messages: list,
                           tools: list | None) -> dict:
        ...

class NonStreamingProvider(ResponseProvider):
    """非流式：一次 chat 返回完整响应"""

    async def get_response(self, agent: "Agent", messages: list,
                           tools: list | None) -> dict:
        response = await agent.llm.chat(
            messages, tools=tools, tool_choice="auto")
        reasoning = response.get("reasoning", "")
        if reasoning and reasoning.strip():
            agent._render_reasoning(reasoning)
        return response

class StreamingProvider(ResponseProvider):
    """流式：thinking 用 Live Panel 逐 token 显示，content 不流"""

    async def get_response(self, agent: "Agent", messages: list,
                           tools: list | None) -> dict:
        import itertools, sys, json as _json
        from rich.live import Live

        assembled: dict = {
            "role": "assistant", "content": "", "reasoning": "",
            "tool_calls": [], "finish_reason": None, "usage": None}
        reasoning_buf = ""
        content_buf = ""
        tc_buf: dict[int, dict] = {}

        spinner = itertools.cycle(
            "\u280b\u2819\u2818\u281c\u2814\u2826\u2827\u2807\u280f")
        stream_think = agent.config.stream_thinking

        panel = Panel("", border_style="dim", title="🧠 Thinking",
                      title_align="left", padding=(0, 1))
        live = Live(panel, console=console, refresh_per_second=10,
                    transient=False)
        live.start()

        try:
            stream = agent.llm.chat_stream(messages, tools=tools)
            async for chunk in stream:
                r = chunk.get("reasoning", "")
                if r:
                    reasoning_buf += r
                    if stream_think:
                        panel = Panel(
                            f"[dim]{reasoning_buf.rstrip()}[/dim]",
                            border_style="dim", title="🧠 Thinking",
                            title_align="left", padding=(0, 1))
                        live.update(panel)
                elif not reasoning_buf and stream_think:
                    live.update(Panel(
                        next(spinner), border_style="dim",
                        title="🧠 Thinking", title_align="left",
                        padding=(0, 1)))
                content_buf += chunk.get("content", "")
                for tc in chunk.get("tool_calls", []):
                    idx = tc["index"]
                    if idx not in tc_buf:
                        tc_buf[idx] = {
                            "id": tc.get("id", ""),
                            "name": tc.get("name", ""),
                            "arguments": ""}
                    if tc.get("id"): tc_buf[idx]["id"] = tc["id"]
                    if tc.get("name"): tc_buf[idx]["name"] = tc["name"]
                    tc_buf[idx]["arguments"] += tc.get("arguments", "")
                if chunk.get("finish_reason"):
                    assembled["finish_reason"] = chunk["finish_reason"]
                if chunk.get("usage"):
                    assembled["usage"] = chunk["usage"]
        finally:
            live.stop()

        assembled["reasoning"] = reasoning_buf
        assembled["content"] = content_buf
        if tc_buf:
            assembled["tool_calls"] = [
                {"id": v["id"], "name": v["name"],
                 "arguments": _json.loads(v["arguments"])
                 if v["arguments"] else {}}
                for v in (tc_buf[i] for i in sorted(tc_buf))
            ]
        logger.debug(
            "stream done: finish=%s content=%d reasoning=%d tool_calls=%d",
            assembled.get("finish_reason"), len(assembled["content"]),
            len(assembled["reasoning"]), len(assembled["tool_calls"]))
        return assembled

class Agent:
    """AI Agent 核心类，负责对话循环与工具调度"""


    def __init__(self, config: OpenMercuryConfig, tool_registry=None, skill_registry=None):
        self.config = config
        self.session = Session()
        self.context = ContextManager(max_tokens=config.max_input_tokens)
        self.tool_registry = tool_registry
        self.skill_registry = skill_registry

        # 初始化 LLM 客户端
        api_key = config.model.api_key or self._get_api_key(config.model.provider)
        self.llm = LLMClient(
            api_key=api_key,
            model=config.model.model,
            base_url=config.model.base_url,
            temperature=config.model.temperature,
            max_tokens=config.model.max_tokens,
            retry_delays=(2, 4),
            cooldown=0.3,  # 请求冷却（秒），0=禁用；共享网关可调大
        )

        self._tool_calls_count = 0
        self._max_tool_calls = self.config.max_tool_calls

        # ── 工厂：根据 config 选响应策略 ──
        if self.config.streaming:
            self._provider: ResponseProvider = StreamingProvider()
        else:
            self._provider: ResponseProvider = NonStreamingProvider()

        # ── Pipeline 初始化 ──
        from .pipeline import (ResultPipeline, TruncationProcessor,
                               SkillViewProcessor, RecoveryPipeline,
                               WaitRecovery, ContextCompressRecovery,
                               EmptyResponsePipeline, CallbackEmptyResponse)
        self.result_pipeline = ResultPipeline()
        self.result_pipeline.use(TruncationProcessor(max_bytes=4000))
        self.result_pipeline.use(SkillViewProcessor())
        self.recovery_pipeline = RecoveryPipeline()
        self.recovery_pipeline.use(WaitRecovery(delay=3.0))
        self.recovery_pipeline.use(ContextCompressRecovery())
        self.empty_response_pipeline = EmptyResponsePipeline()
        self.empty_response_pipeline.use(CallbackEmptyResponse())

        # ── Prompt 构建器 ──
        self.prompt_builder = PromptBuilder()
        self.prompt_builder.use(BasePromptChunk())
        self.prompt_builder.use(SkillsHintChunk())

    async def run(self, prompt: str) -> str:
        """执行一次 Agent 循环"""
        # 添加用户消息
        self.session.add_message("user", prompt)
        self.context.add({"role": "user", "content": prompt})

        tools = self.tool_registry.get_definitions() if self.tool_registry else []
        self.context.set_overhead(self._build_system_prompt(), len(tools))
        if self.context.needs_compression():
            await self._compress_context()

        # 执行 Agent 循环
        return await self._agent_loop()

    def _wrap_up_messages(self, messages):
        """构造收尾消息列表：追加总结请求。"""
        return messages + [{
            "role": "user",
            "content": "已达到最大工具调用次数。请基于已有信息给出最终回复，不要再调用工具。"
        }]

    async def _wrap_up_call(self, messages):
        """收尾调用：无工具文字回应。"""
        try:
            resp = await self.llm.chat(messages, tools=[], tool_choice="none")
        except Exception:
            return "模型调用失败"
        content = resp.get("content", "") or "已达到调用上限。"
        self.session.add_message("assistant", content)
        self.context.add({"role": "assistant", "content": content})
        return content


    async def _agent_loop(self) -> str:
        """Agent 主循环。工具预算耗尽时直接收尾。"""
        self._tool_calls_count = 0
        self._max_tool_calls = self.config.max_tool_calls
        _empty_retries = 0
        _recovery_attempts = 0
        tools = []

        while True:
            messages = self._build_messages()
            tools = list(self.tool_registry.get_definitions() if self.tool_registry else [])

            if self._tool_calls_count >= self._max_tool_calls:
                return await self._wrap_up_call(self._wrap_up_messages(messages))

            logger.debug("→ Agent 循环 #%d: %d 条消息", self._tool_calls_count, len(messages))
            try:
                response = await self._provider.get_response(
                    self, messages, tools or None)
            except Exception as e:
                _recovery_attempts += 1
                if _recovery_attempts > 3:
                    from .self_healing import llm_error
                    return llm_error(e)
                from openai import APIStatusError
                from .pipeline import RecoveryContext
                ctx = RecoveryContext(
                    error=e,
                    status_code=e.status_code if isinstance(e, APIStatusError) else 0,
                    context_tokens=self.context.current_tokens,
                    tool_count=len(tools), model=self.config.model.model)
                if await self.recovery_pipeline.attempt(ctx):
                    if ctx.extra_wait > 0:
                        await asyncio.sleep(ctx.extra_wait)
                    if ctx.compress:
                        await self._compress_context()
                    if ctx.switch_model:
                        logger.info("→ 切换模型: %s", ctx.switch_model)
                        self.llm.model = ctx.switch_model
                    continue
                from .self_healing import llm_error
                return llm_error(e)

            tool_calls = response.get("tool_calls")
            if not tool_calls:
                content = response.get("content", "") or ""
                content = re.sub(r'<\w+:tool_call[^>]*>.*?</\w+:tool_call>', '', content, flags=re.DOTALL).strip()
                reasoning = response.get("reasoning", "")
                if not content:
                    _empty_retries += 1
                    if _empty_retries == 1 and reasoning:
                        from .pipeline import EmptyResponseContext
                        ectx = EmptyResponseContext(
                            reasoning=reasoning, retry_count=_empty_retries)
                        if await self.empty_response_pipeline.attempt(ectx):
                            if ectx.inject_error:
                                self.context.add({"role": "user", "content": ectx.inject_error})
                            console.print("[dim]  \u21bb 空回复 \u2192 回调 LLM…[/dim]")
                            continue
                    content = reasoning or "\uff08\u65e0\u56de\u590d\uff09"
                self.session.add_message("assistant", content)
                self.context.add({"role": "assistant", "content": content})
                return content

            # 校验：过滤不在当前工具列表中的幻觉调用（预算耗尽时 tools 为空，全部拦截）
            valid_names = {t["function"]["name"] for t in tools} if tools else set()
            valid_calls = [tc for tc in tool_calls if tc["name"] in valid_names]
            if len(valid_calls) < len(tool_calls):
                logger.debug("过滤 %d 个幻觉工具调用: %s",
                            len(tool_calls) - len(valid_calls),
                            [tc["name"] for tc in tool_calls if tc["name"] not in valid_names])
            if not valid_calls:
                # 全部是幻觉或无工具可用 → 当作文字回答
                content = response.get("content", "") or ""
                # 清理 LLM 幻觉的工具调用标签
                content = re.sub(r'<\w+:tool_call[^>]*>.*?</\w+:tool_call>', '', content, flags=re.DOTALL)
                content = content.strip()
                if not content:
                    content = "已达到调用上限。"
                self.session.add_message("assistant", content)
                self.context.add({"role": "assistant", "content": content})
                return content
            tool_calls = valid_calls

            # 批量超上限 → 不执行工具，直接收尾
            if self._tool_calls_count + len(tool_calls) > self._max_tool_calls:
                console.print("[dim]  已截停，达到调用上限[/dim]")
                return await self._wrap_up_call(self._wrap_up_messages(self._build_messages()))

            # 执行工具调用
            assistant_content = (response.get("content", "") or "").strip()
            if assistant_content:
                console.print(Panel(Markdown(assistant_content), border_style="dim"))

            api_tool_calls = [
                {
                    "id": tc["id"],
                    "type": "function",
                    "function": {
                        "name": tc["name"],
                        "arguments": json.dumps(tc["arguments"], ensure_ascii=True),
                    },
                }
                for tc in tool_calls
            ]
            assistant_msg = {"role": "assistant", "content": assistant_content, "tool_calls": api_tool_calls}
            self.context.add(assistant_msg)

            logger.debug("⚙ 执行 %d 个工具调用: %s",
                        len(tool_calls),
                        [tc["name"] for tc in tool_calls])

            await self._execute_tool_calls(tool_calls)
            await asyncio.sleep(0.5)

    async def _execute_tool_calls(self, tool_calls: list[dict]):
        """执行一组工具调用"""
        tool_results = []
        exec_contexts = []

        for tc in tool_calls:
            tool_name = tc["name"]
            arguments = tc["arguments"]
            tool_call_id = tc["id"]

            # 构建显示文本
            progress = f"{self._tool_calls_count + 1}/{self._max_tool_calls}"
            arg_parts = [f"{k}={v}" for k, v in arguments.items()]
            arg_str = ", ".join(arg_parts)
            term_w = shutil.get_terminal_size().columns or 80
            # 截断需要为最终状态 `✓ ... 0.0s` 预留空间
            final_line = f"[dim]  ✓ {tool_name} ({progress}) {arg_str}  99.9s[/dim]"
            if len(final_line) >= term_w:
                avail = term_w - len(f"  ✓ {tool_name} ({progress}) ") - 3 - 7
                arg_str = arg_str[:max(0, avail)] + "..."

            if self.tool_registry:
                import time
                t0 = time.monotonic()
                from rich.live import Live
                from rich.text import Text
                with Live(Text.from_markup(f"[bright_black]  ⚙ {tool_name} ({progress}) {arg_str}[/bright_black]"), refresh_per_second=8, transient=False) as live:
                    import itertools
                    spinner = itertools.cycle("⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏")
                    async def _run_with_spinner():
                        task = asyncio.create_task(self.tool_registry.execute(tool_name, **arguments))
                        while not task.done():
                            live.update(Text.from_markup(f"[bright_black]  {next(spinner)} {tool_name} ({progress}) {arg_str}[/bright_black]"))
                            await asyncio.sleep(0.1)
                        return await task
                    result = await _run_with_spinner()
                    elapsed = time.monotonic() - t0
                    live.update(Text.from_markup(f"[bright_black]  ✓ {tool_name} ({progress}) {arg_str}  {elapsed:.1f}s[/bright_black]"))
            else:
                result = {"error": f"Tool '{tool_name}' not available"}

            logger.debug("  ◀ 工具 %s 返回: %s", tool_name, 
                        str(result)[:500])

            tool_results.append({
                "role": "tool",
                "tool_call_id": tool_call_id,
                "content": json.dumps(result, ensure_ascii=True) if not isinstance(result, str) else result,
            })

            self._tool_calls_count += 1

        # 将工具结果添加到上下文
        for tr in tool_results:
            # 截断过长结果，防止上下文爆炸触发 API 拒绝
            content = tr["content"]
            max_len = 4000
            if isinstance(content, str) and len(content) > max_len:
                # 保留前 3500 字 + 截断提示（500 字） = 4000 上限
                tr["content"] = content[:3500] + f"\n... (结果过长，已截断 {len(content) - 3500} 字符)"
            self.context.add(tr)

    def _build_messages(self) -> list[dict]:
        """构建发送给 LLM 的消息列表"""
        messages = [
            {"role": "system", "content": self._build_system_prompt()},
        ]

        # 添加上下文窗口中的消息
        messages.extend(self.context.get_window())

        return messages

    def _build_system_prompt(self) -> str:
        return self.prompt_builder.build(self)

    async def _compress_context(self):
        """压缩上下文"""
        from openmercury.memory.compressor import ContextCompressor

        compressor = ContextCompressor(
            max_input_tokens=self.config.max_input_tokens,
            threshold=self.config.compression_threshold,
        )

        async def llm_summary(messages: list[dict]) -> str:
            """LLM 生成语义摘要——保留用户意图 + 关键决策"""
            lines = []
            for m in messages:
                role = m.get("role", "unknown")
                content = m.get("content", "")
                if isinstance(content, str) and content.strip():
                    # tool 结果只取前 200 字
                    text = content[:200] if role == "tool" else content[:600]
                    lines.append(f"[{role}]: {text}")

            prompt = (
                "Summarize this conversation segment into one concise paragraph "
                "(under 150 words). Include: what the user asked, what tools were "
                "used, key findings or decisions. Use natural language, not bullet "
                "points.\n\n"
                + "\n".join(lines[-30:])  # 最多 30 条
                + "\n\nSummary:"
            )
            try:
                response = await self.llm.chat(
                    [{"role": "user", "content": prompt}], tools=[]
                )
                content = response.get("content", "").strip()
                return f"[Earlier conversation summary]: {content}"
            except Exception as e:
                logger.warning("LLM summary failed: %s", e)
                return f"[{len(messages)} earlier messages — summary unavailable]"

        compressed = await compressor.compress(
            self.context.messages,
            strategy="sliding",
            summary_fn=llm_summary,
        )
        self.context.messages = compressed
        self.context.current_tokens = sum(
            self.context._estimate_tokens(m) for m in compressed
        )
        console.print("[dim]→ Context compressed (LLM summarized)[/dim]")

    @staticmethod
    def _render_reasoning(reasoning: str) -> None:
        """非流式：渲染 thinking 面板"""
        text = reasoning.strip()
        if not text:
            return
        console.print(Panel(f"[dim]{text}[/dim]", border_style="dim",
                      title="🧠 Thinking", title_align="left", padding=(0, 1)))

    def reset(self):
        """重置会话"""
        self.session = Session()
        self.context = ContextManager(max_tokens=self.config.model.max_tokens * 2)
        self._tool_calls_count = 0

    @staticmethod
    def _get_api_key(provider: str) -> str:
        """从环境变量获取 API Key——由 PROVIDER_REGISTRY 驱动"""
        import os
        from .config import PROVIDER_REGISTRY
        entry = PROVIDER_REGISTRY.get(provider, {})
        key_env = entry.get("key_env", "")
        return os.environ.get(key_env, "") if key_env else ""

class AgentLoop:
    """Agent 循环控制器 - 管理多轮对话"""

    def __init__(self, agent: Agent):
        self.agent = agent
        self.history = []

    async def step(self, message: str) -> dict:
        """执行单步循环"""
        response = await self.agent.run(message)
        self.history.append({"user": message, "assistant": response})
        return {"response": response, "history_length": len(self.history)}

    def reset(self):
        """重置循环"""
        self.history = []
        self.agent.reset()
