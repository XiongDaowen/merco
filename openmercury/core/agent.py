"""Agent 主循环与核心逻辑"""

import json
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

When you need to perform actions, use the available tools. Always be concise and helpful."""

    def __init__(self, config: OpenMercuryConfig, tool_registry=None, skill_registry=None):
        self.config = config
        self.session = Session()
        self.context = ContextManager(max_tokens=config.model.max_tokens * 2)
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
        self._max_tool_calls = config.max_tool_calls

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

    async def _agent_loop(self) -> str:
        """Agent 主循环 - 支持连续工具调用"""
        self._tool_calls_count = 0

        while self._tool_calls_count < self._max_tool_calls:
            # 构建消息
            messages = self._build_messages()

            # 获取工具定义
            tools = None
            if self.tool_registry:
                tools = self.tool_registry.get_definitions()

            # 调用 LLM（SDK 自带智能重试，含 Retry-After 支持）
            logger.debug("→ Agent 循环 #%d: 发送 %d 条消息", 
                         self._tool_calls_count, len(messages))
            try:
                response = await self.llm.chat(messages, tools=tools)
            except Exception as e:
                # 记录失败时的上下文状态，帮助诊断
                logger.error("✗ Agent 循环 #%d 失败: %s", 
                            self._tool_calls_count, str(e))
                logger.error("  当前上下文: %d 条消息", len(self.context.messages))
                logger.error("  工具调用计数: %d", self._tool_calls_count)
                raise

            # 检查是否有工具调用
            tool_calls = response.get("tool_calls")
            logger.debug("← LLM 响应: %s", 
                        "工具调用" if tool_calls else "文本回复")

            if not tool_calls:
                # 没有工具调用，直接返回回复
                content = response.get("content", "")
                self.session.add_message("assistant", content)
                self.context.add({"role": "assistant", "content": content})
                logger.debug("✓ 最终回复: %s", content[:200])
                return content

            # 执行工具调用
            # 保留 LLM 可能同时返回的文字（如 "让我搜索一下..."）
            assistant_content = response.get("content", "")
            if assistant_content:
                console.print(Panel(Markdown(assistant_content), border_style="dim"))

            # 转换为 OpenAI 标准格式: {id, type, function: {name, arguments}}
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
            # 工具执行后稍作停顿，防止连续请求触发突发限制
            await asyncio.sleep(0.5)

        # 达到最大调用次数：让 LLM 基于已有信息收尾，而非硬报错
        self.context.add({
            "role": "user",
            "content": (
                "你已达到工具调用上限。请根据目前已获取的信息，"
                "简洁地总结你的发现并给出最终回答。不要再调用工具。"
            ),
        })
        try:
            response = await self.llm.chat(self._build_messages(), tools=[])
        except Exception:
            return "已达到最大工具调用次数，且无法让模型收尾。请简化任务后重试。"

        content = response.get("content", "")
        self.session.add_message("assistant", content)
        self.context.add({"role": "assistant", "content": content})
        return content

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

        compressor = ContextCompressor()
        compressed = await compressor.compress(
            self.context.messages,
            strategy="summary",
        )
        self.context.messages = compressed
        self.context.current_tokens = sum(
            self.context._estimate_tokens(m) for m in compressed
        )
        console.print("[dim]→ Context compressed[/dim]")

    def reset(self):
        """重置会话"""
        self.session = Session()
        self.context = ContextManager(max_tokens=self.config.model.max_tokens * 2)
        self._tool_calls_count = 0

    @staticmethod
    def _get_api_key(provider: str) -> str:
        """从环境变量获取 API Key"""
        import os

        provider_keys = {
            "openai": os.environ.get("OPENAI_API_KEY", ""),
            "anthropic": os.environ.get("ANTHROPIC_API_KEY", ""),
            "openrouter": os.environ.get("OPENROUTER_API_KEY", ""),
        }

        return provider_keys.get(provider, "")


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
