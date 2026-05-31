"""Agent 主循环与核心逻辑"""

import json
import re
import asyncio
import logging
import shutil
import time
from typing import Optional
from abc import ABC, abstractmethod
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from .config import MercoConfig
from .llm import LLMClient
from .session import Session
from .message import Message, MessageRole
from .context import ContextManager, msg_tokens, estimate_tokens as est_tk
from .pipeline import ProcessContext
from .interrupt import (
    InterruptCleanupPipeline, CleanupContext,
    InjectCancelMessages, TerminateSubprocesses,
    CloseMCPConnections, EmitInterruptHooks, SavePartialState
)

console = Console()
logger = logging.getLogger("merco.agent")

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
    PROMPT = """You are Mercury Code, an AI coding assistant. You can help with:
- Writing and editing code
- Answering questions about the codebase
- Executing shell commands
- Searching and managing files

When you need to perform actions, use the available tools.
Always be concise and helpful."""
    def build(self, agent) -> str: return self.PROMPT

class SkillsHintChunk(PromptChunk):
    """skill 自动注入：根据当前对话内容匹配相关 skill，注入提示到 system prompt"""
    name = "skills_hint"

    def enabled(self, agent) -> bool:
        return bool(agent.skill_registry and agent.skill_registry.list_skills())

    def build(self, agent) -> str:
        registry = agent.skill_registry
        if not registry:
            return ""
        prompt = getattr(agent, "_current_prompt", "")
        if not prompt:
            return "使用 skill_view 工具可以加载项目相关的技能说明文档。"

        relevant = registry.get_relevant(prompt)
        if not relevant:
            return ""

        parts = []
        for skill in relevant:
            parts.append(
                f"## 相关技能: {skill['name']}\n"
                f"{skill['content']}\n"
                f"（已自动加载。更多技能用 skill_view 查看。）"
            )
        return "\n\n".join(parts)


class TimeContextChunk(PromptChunk):
    name = "time_context"
    def build(self, agent) -> str:
        import datetime
        now = datetime.datetime.now()
        return (
            f"当前时间: {now.strftime('%Y-%m-%d %H:%M:%S')} "
            f"{now.astimezone().tzinfo or 'local'}  "
            f"星期{['一','二','三','四','五','六','日'][now.weekday()]}"
        )


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
        import sys, json as _json
        from rich.live import Live

        assembled: dict = {
            "role": "assistant", "content": "", "reasoning": "",
            "tool_calls": [], "finish_reason": None, "usage": None}
        reasoning_buf = ""
        content_buf = ""
        tc_buf: dict[int, dict] = {}

        stream_think = agent.config.stream_thinking

        # ── 初始等待提示（无 reasoning 时显示"⏳ 思考中…"，有则显示推理文字）──
        panel = Panel("[dim]⏳ 思考中…[/dim]", border_style="dim",
                      title="🧠 Thinking", title_align="left", padding=(0, 1))
        live = Live(panel, console=console, refresh_per_second=10,
                    transient=True)
        live.start()

        try:
            stream = agent.llm.chat_stream(messages, tools=tools)
            async for chunk in stream:
                # 取消检查点：如果任务被取消，立即退出
                current = asyncio.current_task()
                if current and current.cancelled():
                    live.stop()
                    # TODO: 此 checkpoint 无法覆盖「Cancel 在 __anext__ I/O 等待中到达」的情况
                    #      补救方案：加 except asyncio.CancelledError 兜底 handler，抽离保存逻辑。
                    #      优先级：低——窗口极小且用户主动取消，丢失的 partial content 是预期行为。
                    # 保存部分响应
                    assembled["reasoning"] = reasoning_buf
                    assembled["content"] = content_buf
                    if tc_buf:
                        assembled["tool_calls"] = [
                            {"id": v["id"], "name": v["name"],
                             "arguments": _json.loads(v["arguments"])
                             if v["arguments"] else {}}
                            for v in (tc_buf[i] for i in sorted(tc_buf))
                        ]
                    # 将部分响应添加到 context 和 session
                    if reasoning_buf or content_buf or tc_buf:
                        assistant_msg = {
                            "role": "assistant",
                            "content": content_buf,
                            "reasoning": reasoning_buf,
                        }
                        if tc_buf:
                            assistant_msg["tool_calls"] = assembled["tool_calls"]
                        agent.context.add(assistant_msg)
                        agent.session.add_message("assistant", content_buf,
                                                  reasoning=reasoning_buf,
                                                  tool_calls=assembled.get("tool_calls"))
                    raise asyncio.CancelledError()
                r = chunk.get("reasoning", "")
                if r:
                    reasoning_buf += r
                    if stream_think:
                        live.update(Panel(
                            f"[dim]{reasoning_buf.rstrip()}[/dim]",
                            border_style="dim", title="🧠 Thinking",
                            title_align="left", padding=(0, 1)))
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
            if live:
                live.stop()
            # 用普通 console.print 留最后面板，避免 Live 残留干扰键盘输入
            if reasoning_buf:
                console.print(Panel(
                    f"[dim]{reasoning_buf.rstrip()}[/dim]",
                    border_style="dim", title="🧠 Thinking",
                    title_align="left", padding=(0, 1)))

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


    def __init__(self, config: MercoConfig, tool_registry=None, skill_registry=None):
        self.config = config
        self.session = Session()
        from merco.sandbox import snapshot
        snapshot.set_current_session(self.session.id)
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
            cooldown=0.3,  # 请求冷却（秒），0=禁用；共享网关可调大
        )

        self._tool_calls_count = 0
        self._max_tool_calls = self.config.max_tool_calls
        self._current_prompt = ""

        # ── 可观察性 ──
        from merco.hooks.registry import HookRegistry
        from merco.observability.observer import Observer
        self.hooks = HookRegistry()
        self.observer = Observer(self.hooks)

        # ── 守卫：敏感命令执行前确认 ──
        from merco.sandbox.guard import ToolGuard
        self.guard = ToolGuard(
            mode=config.sandbox_mode,
            user_rules=config.sandbox_rules,
        )

        # ── 会话持久化 ──
        from merco.memory.session_store import SessionStore
        from merco.memory.session_search import SessionSearch
        self._session_store = SessionStore(_get_db_path())
        self._search = SessionSearch(self._session_store)
        self.session = Session.resume_or_create(self._session_store)
        self._restore_context()

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
        self.result_pipeline.use(TruncationProcessor(max_bytes=16000))
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
        self.prompt_builder.use(TimeContextChunk())

        # ── Memory 召回 ──
        from merco.memory.recall import HybridRecaller, FTS5Recaller, MemoryRecaller
        from merco.memory.store import MemoryStore

        _fts5 = FTS5Recaller(self._search)
        _mem = MemoryRecaller(MemoryStore(config.memory_path))
        self.recaller = (
            HybridRecaller(limit=config.memory_recall_limit, max_chars=config.memory_recall_max_chars)
            .add(_fts5)
            .add(_mem)
        )

        # ── MCP 客户端 ──
        from merco.mcp.manager import MCPServerManager
        self.mcp_manager = MCPServerManager(
            tool_registry=self.tool_registry,
            hooks=self.hooks,
        )

        # ── 中断清理管线 ──
        self._cleanup_pipeline = (InterruptCleanupPipeline()
            .use(InjectCancelMessages())
            .use(TerminateSubprocesses())
            .use(CloseMCPConnections())
            .use(EmitInterruptHooks())
            .use(SavePartialState()))

    async def run(self, prompt: str) -> str:
        """执行一次 Agent 循环"""
        self._current_prompt = prompt
        # 添加用户消息
        self.session.add_message("user", prompt)
        self.context.add({"role": "user", "content": prompt})

        tools = self.tool_registry.get_definitions() if self.tool_registry else []
        self.context.set_overhead(await self._build_system_prompt(), len(tools))
        if self.context.needs_compression():
            await self._compress_context()

        # 执行 Agent 循环
        try:
            result = await self._agent_loop()
        except asyncio.CancelledError:
            # 使用 InterruptCleanupPipeline 替换 _inject_interrupted_tool_results
            cancelled_tool_calls = self._find_orphan_tool_calls()
            cleanup_ctx = CleanupContext(
                agent=self,
                cancelled_tool_calls=cancelled_tool_calls,
                session_id=self.session.id,
            )
            await self._cleanup_pipeline.process(cleanup_ctx)
            raise
        self._auto_title(prompt)
        self.session.metadata["observer"] = self.observer.snapshot()
        self.session.save()
        self._session_store.save_metadata(self.session.id, self.session.metadata)
        await self.hooks.emit("conversation.turn")
        return result

    def _restore_context(self):
        """清空上下文，然后从持久化会话恢复消息"""
        self.context = ContextManager(max_tokens=self.config.max_input_tokens)
        snap = self.session.metadata.get("observer")
        if snap:
            self.observer.restore(snap)

        checkpoint = self.session.metadata.get("compress_checkpoint")
        if checkpoint:
            # Restore from checkpoint: summary + tail only
            summary = checkpoint.get("summary", "")
            tail_count = checkpoint.get("tail_count", 2)
            all_msgs = self.session.messages
            tail = all_msgs[-tail_count * 2:] if len(all_msgs) > tail_count * 2 else all_msgs  # ~2 msgs per turn

            if summary:
                self.context.add({"role": "system", "content": summary})
            for msg in tail:
                entry = {"role": msg["role"], "content": msg.get("content", "")}
                if msg.get("tool_call_id"):
                    entry["tool_call_id"] = msg["tool_call_id"]
                if msg.get("tool_calls"):
                    entry["tool_calls"] = msg["tool_calls"]
                self.context.add(entry)
            return

        for msg in self.session.messages:
            entry = {"role": msg["role"], "content": msg.get("content", "")}
            if msg.get("tool_call_id"):
                entry["tool_call_id"] = msg["tool_call_id"]
            if msg.get("tool_calls"):
                entry["tool_calls"] = msg["tool_calls"]
            self.context.add(entry)

    def _auto_title(self, user_input: str):
        """用首条用户消息的前 40 字作为会话标题"""
        if self.session.title or not user_input:
            return
        title = user_input.strip()[:40]
        self.session.title = title
        self._session_store.update_title(self.session.id, title)

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
            messages = await self._build_messages()
            tools = list(self.tool_registry.get_definitions() if self.tool_registry else [])

            if self._tool_calls_count >= self._max_tool_calls:
                return await self._wrap_up_call(self._wrap_up_messages(messages))

            logger.debug("→ Agent 循环 #%d: %d 条消息", self._tool_calls_count, len(messages))
            t0 = time.monotonic()
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

            # 记录 API 返回的实测 token（流式可能无 usage，fallback 到估算值）
            usage = response.get("usage")
            if usage and usage.get("prompt_tokens"):
                self.context.last_actual_tokens = usage["prompt_tokens"]

            tokens_in = usage.get("prompt_tokens") if usage else self.context.total_tokens
            tokens_out = usage.get("completion_tokens") if usage else est_tk(
                (response.get("content") or "") + (response.get("reasoning") or ""))

            await self.hooks.emit("llm.chat",
                                   duration=time.monotonic() - t0,
                                   tokens_in=tokens_in,
                                   tokens_out=tokens_out,
                                   cached_tokens=usage.get("cached_tokens", 0) if usage else 0,
                                   cache_read_tokens=usage.get("cache_read_tokens", 0) if usage else 0)

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
                return await self._wrap_up_call(self._wrap_up_messages(await self._build_messages()))

            await self._dispatch_tool_calls(tool_calls, response)
            await asyncio.sleep(0.5)

    def _find_orphan_tool_calls(self) -> list[dict]:
        """查找孤儿 tool_calls（未完成的）。"""
        completed_ids = set()
        for msg in self.context.messages:
            if msg.get("tool_call_id"):
                completed_ids.add(msg["tool_call_id"])

        orphans = []
        for msg in reversed(self.context.messages):
            if msg.get("role") != "assistant":
                continue
            for tc in (msg.get("tool_calls") or []):
                tc_id = tc.get("id") if isinstance(tc, dict) else None
                if tc_id and tc_id not in completed_ids:
                    orphans.append(tc)
        return orphans

    async def _dispatch_tool_calls(self, tool_calls: list[dict], response: dict) -> None:
        """工具调度：渲染内容 → 写上下文 → 执行工具"""
        assistant_content = (response.get("content", "") or "").strip()
        if assistant_content:
            console.print(Panel(Markdown(assistant_content), border_style="dim"))
        api_tool_calls = [
            {"id": tc["id"], "type": "function",
             "function": {"name": tc["name"], "arguments": json.dumps(tc["arguments"], ensure_ascii=True)}}
            for tc in tool_calls
        ]
        self.context.add({"role": "assistant", "content": assistant_content, "tool_calls": api_tool_calls})
        self.session.add_message("assistant", assistant_content, tool_calls=api_tool_calls)
        logger.debug("⚙ 执行 %d 个工具调用: %s", len(tool_calls), [tc["name"] for tc in tool_calls])
        await self._execute_tool_calls(tool_calls)

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

            # ── 守卫检查 ──
            t0 = time.monotonic()
            approved = await self.guard.check(tool_name, arguments)
            if not approved:
                result = {"error": "操作已被拦截或取消"}

            elif self.tool_registry:

                _INTERACTIVE_TOOLS = {"edit_file"}  # 会弹确认提示的工具，不能用 spinner（会覆盖终端）
                if tool_name in _INTERACTIVE_TOOLS:
                    console.print(f"[bright_black]  ⚙ {tool_name} ({progress}) {arg_str}[/bright_black]")
                    result = await self.tool_registry.execute(tool_name, **arguments)
                    elapsed = time.monotonic() - t0
                    console.print(f"[bright_black]  ✓ {tool_name} ({progress}) {arg_str}  {elapsed:.1f}s[/bright_black]")
                else:
                    from rich.live import Live
                    from rich.text import Text
                    import itertools
                    with Live(Text.from_markup(f"[bright_black]  ⚙ {tool_name} ({progress}) {arg_str}[/bright_black]"), refresh_per_second=8, transient=False) as live:
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

            # ── 可观察性 ──
            elapsed = time.monotonic() - t0
            if "error" in result:
                await self.hooks.emit("tool.error", tool_name=tool_name,
                                      error=result.get("error", ""))
            else:
                await self.hooks.emit("tool.after_execute", tool_name=tool_name,
                                      duration=elapsed)

            # ── Pipeline 处理 ──
            tool = self.tool_registry.get(tool_name) if self.tool_registry else None
            pctx = ProcessContext(
                tool_name=tool_name, arguments=arguments, result=result,
                tool_schema=getattr(tool, 'parameters', None),
                tool_call_id=tool_call_id)
            await self.result_pipeline.process(pctx)
            if isinstance(pctx.result, str):
                content = pctx.result
            else:
                try:
                    content = json.dumps(pctx.result, ensure_ascii=False)
                except (TypeError, ValueError):
                    content = str(pctx.result)
            tool_results.append({
                "role": "tool",
                "tool_call_id": tool_call_id,
                "content": content})
            exec_contexts.append(pctx)
            self._tool_calls_count += 1

        for tr in tool_results:
            self.context.add(tr)
            self.session.add_message("tool", tr["content"],
                                     tool_call_id=tr.get("tool_call_id", ""))
        for pctx in exec_contexts:
            for msg in pctx.extra_messages:
                self.context.add(msg)

    async def _build_messages(self) -> list[dict]:
        """构建发送给 LLM 的消息列表"""
        messages = [
            {"role": "system", "content": await self._build_system_prompt()},
        ]

        # 添加上下文窗口中的消息
        messages.extend(self.context.get_window())

        return messages

    async def _build_system_prompt(self) -> str:
        base = self.prompt_builder.build(self)

        if self.config.memory_recall_enabled and self._current_prompt:
            try:
                recalled = await self.recaller.recall(self._current_prompt)
                if recalled:
                    lines = ["\n## 相关历史对话（仅供参考）"]
                    for i, r in enumerate(recalled, 1):
                        lines.append(f"{i}. [{r.session_title}] {r.snippet}")
                    base += "\n".join(lines)
            except Exception:
                logging.getLogger("merco.agent").debug("Memory recall failed", exc_info=True)

        return base

    async def _compress_context(self):
        """压缩上下文"""
        # Auto-fork: save complete copy before compressing
        if self.config.fork_enabled and self.config.fork_auto_on_compress:
            try:
                self.session.save()
                archived_id = self._session_store.clone_session(self.session.id)
                console.print(f"[dim]📦 原会话已归档: {archived_id[:8]}[/dim]")
            except Exception:
                logger.debug("Auto-fork failed", exc_info=True)

        from merco.memory.compressor import ContextCompressor

        compressor = ContextCompressor(
            max_input_tokens=self.config.max_input_tokens,
            threshold=self.config.compression_threshold,
        )

        summary_result = None

        async def llm_summary(messages: list[dict]) -> str:
            """LLM 生成语义摘要——保留用户意图 + 关键决策"""
            nonlocal summary_result
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
                summary_result = f"[Earlier conversation summary]: {content}"
                return summary_result
            except Exception as e:
                logger.warning("LLM summary failed: %s", e)
                fallback = f"[{len(messages)} earlier messages — summary unavailable]"
                summary_result = fallback
                return fallback

        compressed = await compressor.compress(
            self.context.messages,
            strategy="sliding",
            summary_fn=llm_summary,
        )
        self.context.messages = compressed
        self.context.current_tokens = sum(
            msg_tokens(m) for m in compressed
        )
        # Store compression checkpoint so restart doesn't re-expand
        self.session.metadata["compress_checkpoint"] = {
            "summary": summary_result or "",
            "compressed_at": time.time(),
            "original_count": len(self.session.messages),
            "tail_count": 2,  # same as TAIL_TURNS in compressor
        }
        console.print("[dim]→ Context compressed (LLM summarized)[/dim]")
        console.print("[dim]→ 用 /history 查看完整记录[/dim]")

    @staticmethod
    def _render_reasoning(reasoning: str) -> None:
        """非流式：渲染 thinking 面板"""
        text = reasoning.strip()
        if not text:
            return
        console.print(Panel(f"[dim]{text}[/dim]", border_style="dim",
                      title="🧠 Thinking", title_align="left", padding=(0, 1)))

    def get_context_stats(self) -> dict:
        """上下文窗口使用统计，供 REPL 进度条渲染"""
        max_tokens = self.config.max_input_tokens
        actual = getattr(self.context, "last_actual_tokens", 0)
        current = actual if actual > 0 else self.context.total_tokens
        ratio = min(current / max_tokens, 1.0) if max_tokens > 0 else 0
        return {
            "current": current, "max": max_tokens, "ratio": ratio,
            "threshold": self.config.compression_threshold,
            "is_estimate": actual == 0,
            "tool_count": self._tool_calls_count,
            "max_tool_calls": self._max_tool_calls,
        }

    def reset(self):
        """重置会话：新建 session + 清空上下文"""
        self.session = Session(store=self._session_store)
        self._session_store.create_session(self.session.id)
        self.context = ContextManager(max_tokens=self.config.max_input_tokens)
        self._tool_calls_count = 0
        self._current_prompt = ""

    @staticmethod
    def _get_api_key(provider: str) -> str:
        """从环境变量获取 API Key——由 PROVIDER_REGISTRY 驱动"""
        import os
        from .config import PROVIDER_REGISTRY
        entry = PROVIDER_REGISTRY.get(provider)
        if entry:
            return os.environ.get(entry.key_env, "")
        return ""

def _get_db_path() -> str:
    """跟随配置路径确定 sessions.db 位置"""
    import os
    from pathlib import Path

    for candidate in [Path("./.merco"), Path(os.path.expanduser("~/.merco"))]:
        if candidate.exists() or candidate.parent.exists():
            candidate.mkdir(parents=True, exist_ok=True)
            return str(candidate / "sessions.db")

    path = Path(os.path.expanduser("~/.merco"))
    path.mkdir(parents=True, exist_ok=True)
    return str(path / "sessions.db")


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
