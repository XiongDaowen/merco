"""LLM 客户端 - OpenAI 兼容接口"""

import json
from typing import Optional, AsyncIterator
from openai import AsyncOpenAI


class LLMClient:
    """OpenAI 兼容的 LLM 客户端"""

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4",
        base_url: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ):
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens

        client_kwargs = {"api_key": api_key}
        if base_url:
            client_kwargs["base_url"] = base_url

        self.client = AsyncOpenAI(**client_kwargs)

    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] = None,
        tool_choice: str = "auto",
    ) -> dict:
        """发送聊天请求并获取响应"""
        params = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }

        if tools:
            params["tools"] = tools
            params["tool_choice"] = tool_choice

        response = await self.client.chat.completions.create(**params)
        return self._parse_response(response)

    async def chat_stream(
        self,
        messages: list[dict],
        tools: list[dict] = None,
        tool_choice: str = "auto",
    ) -> AsyncIterator[dict]:
        """流式聊天"""
        params = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": True,
        }

        if tools:
            params["tools"] = tools
            params["tool_choice"] = tool_choice

        stream = await self.client.chat.completions.create(**params)

        async for chunk in stream:
            parsed = self._parse_chunk(chunk)
            if parsed:
                yield parsed

    @staticmethod
    def _parse_response(response) -> dict:
        """解析完整响应"""
        choice = response.choices[0]
        message = choice.message

        result = {
            "role": message.role,
            "content": message.content or "",
            "finish_reason": choice.finish_reason,
        }

        if message.tool_calls:
            result["tool_calls"] = [
                {
                    "id": tc.id,
                    "name": tc.function.name,
                    "arguments": json.loads(tc.function.arguments),
                }
                for tc in message.tool_calls
            ]

        return result

    @staticmethod
    def _parse_chunk(chunk) -> Optional[dict]:
        """解析流式块"""
        choice = chunk.choices[0] if chunk.choices else None
        if not choice:
            return None

        delta = choice.delta
        result = {}

        if delta.content:
            result["content"] = delta.content

        if delta.tool_calls:
            result["tool_calls"] = [
                {
                    "index": tc.index,
                    "id": tc.id,
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                }
                for tc in delta.tool_calls
            ]

        if choice.finish_reason:
            result["finish_reason"] = choice.finish_reason

        return result if result else None
