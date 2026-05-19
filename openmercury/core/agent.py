"""Agent 主循环与核心逻辑"""

import json
from typing import Optional
from rich.console import Console

from .config import OpenMercuryConfig
from .llm import LLMClient
from .session import Session
from .message import Message, MessageRole
from .context import ContextManager


console = Console()


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
        )

        self._tool_calls_count = 0
        self._max_tool_calls = 10  # 防止无限工具调用循环

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

            # 调用 LLM
            response = await self.llm.chat(messages, tools=tools)

            # 检查是否有工具调用
            tool_calls = response.get("tool_calls")

            if not tool_calls:
                # 没有工具调用，直接返回回复
                content = response.get("content", "")
                self.session.add_message("assistant", content)
                self.context.add({"role": "assistant", "content": content})
                return content

            # 执行工具调用
            await self._execute_tool_calls(tool_calls)

        return "Error: Maximum tool call iterations reached"

    async def _execute_tool_calls(self, tool_calls: list[dict]):
        """执行一组工具调用"""
        tool_results = []

        for tc in tool_calls:
            tool_name = tc["name"]
            arguments = tc["arguments"]
            tool_call_id = tc["id"]

            console.print(f"[dim]→ Calling tool: {tool_name}({json.dumps(arguments)})[/dim]")

            # 执行工具
            if self.tool_registry:
                result = await self.tool_registry.execute(tool_name, **arguments)
            else:
                result = {"error": f"Tool '{tool_name}' not available"}

            tool_results.append({
                "role": "tool",
                "tool_call_id": tool_call_id,
                "content": json.dumps(result, ensure_ascii=False) if not isinstance(result, str) else result,
            })

            self._tool_calls_count += 1

        # 将工具结果添加到上下文
        for tr in tool_results:
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
