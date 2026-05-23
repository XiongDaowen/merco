"""Agent 主循环与核心逻辑"""

import json
import re
import asyncio
import logging
import shutil
from typing import Optional
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from .config import OpenMercuryConfig
from .llm import LLMClient
from .session import Session
from .message import Message, MessageRole
from .context import ContextManager


console = Console()
logger = logging.getLogger("openmercury.agent")


class Agent:
    """AI Agent 核心类，负责对话循环与工具调度"""

    SYSTEM_PROMPT = """You are OpenMercury, an AI coding assistant. You can help with:
- Writing and editing code
- Answering questions about the codebase
- Executing shell commands
- Searching and managing files

When you need to perform actions, use the available tools.
Always be concise and helpful."""

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

    async def run(self, prompt: str) -> str:
        """执行一次 Agent 循环"""
        # 添加用户消息
        self.session.add_message("user", prompt)
        self.context.add({"role": "user", "content": prompt})

        # 检查是否需要压缩上下文
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

        while True:
            messages = self._build_messages()
            tools = self.tool_registry.get_definitions() if self.tool_registry else []
            tools = list(tools)

            if self._tool_calls_count >= self._max_tool_calls:
                return await self._wrap_up_call(self._wrap_up_messages(messages))

            logger.debug("→ Agent 循环 #%d: 发送 %d 条消息",
                        self._tool_calls_count, len(messages))
            try:
                response = await self.llm.chat(messages, tools=tools or None, tool_choice="auto")
            except Exception as e:
                logger.error("✗ Agent 循环 #%d 失败: %s",
                            self._tool_calls_count, str(e))
                return f"模型调用失败：{e}"

            tool_calls = response.get("tool_calls")
            if not tool_calls:
                content = response.get("content", "") or ""
                # 清理 LLM 幻觉的工具调用语法（通用匹配）
                content = re.sub(r'<\w+:tool_call[^>]*>.*?</\w+:tool_call>', '', content, flags=re.DOTALL)
                content = content.strip()
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
            assistant_content = response.get("content", "")
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
        """构建系统提示"""
        prompt = self.SYSTEM_PROMPT

        # 注入技能（如果有）
        if self.skill_registry:
            skills = self.skill_registry.list_skills()
            if skills:
                prompt += "\n\n## Available Skills\n\n"
                for skill in skills:
                    prompt += f"### {skill['name']}\n{skill.get('description', '')}\n\n"
                    prompt += f"{skill['content'][:500]}...\n\n"

        return prompt

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
