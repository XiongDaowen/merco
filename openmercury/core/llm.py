"""LLM 客户端 - OpenAI 兼容接口"""
import json
import logging
import re
import time
import asyncio
from typing import Any, Optional, AsyncIterator
from openai import AsyncOpenAI


logger = logging.getLogger("openmercury.llm")


# 清理字符串中的代理对字符（surrogates），防止 API 序列化崩溃
_SURROGATE_RE = re.compile(r'[\ud800-\udfff]')


def _clean_surrogates(obj):
    """递归清理数据结构中的代理对字符"""
    if isinstance(obj, str):
        return _SURROGATE_RE.sub('', obj)
    if isinstance(obj, list):
        return [_clean_surrogates(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _clean_surrogates(v) for k, v in obj.items()}
    return obj


def _extract_reasoning(message) -> str:
    """从 API 响应的 model_extra 中提取 reasoning（CoT 推理）。"""
    try:
        extra = getattr(message, "model_extra", None)
        if isinstance(extra, dict):
            rc = extra.get("reasoning_content") or extra.get("reasoning") or ""
            if rc:
                return str(rc)
    except Exception:
        pass
    return ""


class LLMClient:
    """OpenAI 兼容的 LLM 客户端 — 纯传输层，重试/恢复由 Agent RecoveryPipeline 统一处理"""

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4",
        base_url: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        cooldown: float = 0,  # 请求最小间隔（秒），0=不禁用
    ):
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.cooldown = cooldown
        self._last_request_time = 0.0

        client_kwargs = {
            "api_key": api_key,
            "max_retries": 0,
        }
        if base_url:
            client_kwargs["base_url"] = base_url

        self.client = AsyncOpenAI(**client_kwargs)

    # ── 公共方法 ─────────────────────────────────────────────────

    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] = None,
        tool_choice: str | dict[str, Any] = "auto",
    ) -> dict:
        """非流式聊天"""
        params = self._build_params(messages, tools, tool_choice)
        response = await self._request(params)
        result = self._parse_response(response)
        logger.debug("← API 响应: finish=%s content_len=%d tool_calls=%d",
                     result.get("finish_reason"), len(result.get("content", "")),
                     len(result.get("tool_calls", [])))
        return result

    async def chat_stream(
        self,
        messages: list[dict],
        tools: list[dict] = None,
        tool_choice: str | dict[str, Any] = "auto",
    ) -> AsyncIterator[dict]:
        """流式聊天"""
        params = self._build_params(messages, tools, tool_choice, stream=True)
        stream = await self._request(params)
        assert stream is not None
        async for chunk in stream:
            if parsed := self._parse_chunk(chunk):
                yield parsed

    # ── 私有方法 ─────────────────────────────────────────────────

    def _build_params(
        self, messages: list[dict], tools: list[dict] | None,
        tool_choice: str | dict[str, Any], stream: bool = False,
    ) -> dict:
        """构造 API 请求参数"""
        params = {
            "model": self.model,
            "messages": _clean_surrogates(messages),
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        if stream:
            params["stream"] = True
        if tools:
            params["tools"] = tools
            params["tool_choice"] = tool_choice
        return params

    async def _request(self, params: dict):
        """发送请求（含 cooldown），不重试。错误原样上抛交 Agent RecoveryPipeline。"""
        logger.debug("→ API 请求: model=%s messages=%d tools=%d",
                     self.model, len(params.get("messages", [])),
                     len(params.get("tools", [])))

        if self.cooldown > 0:
            elapsed = time.monotonic() - self._last_request_time
            if elapsed < self.cooldown:
                wait = self.cooldown - elapsed
                logger.debug("⏳ 冷却 %.1fs（距上次请求 %.1fs）", wait, elapsed)
                await asyncio.sleep(wait)

        response = await self.client.chat.completions.create(**params)
        self._last_request_time = time.monotonic()
        return response

    @staticmethod
    def _parse_response(response) -> dict:
        """解析完整响应"""
        choice = response.choices[0]
        message = choice.message

        result = {
            "role": message.role,
            "content": message.content or "",
            "reasoning": _extract_reasoning(message),
            "finish_reason": choice.finish_reason,
            "usage": {
                "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                "completion_tokens": response.usage.completion_tokens if response.usage else 0,
                "total_tokens": response.usage.total_tokens if response.usage else 0,
            },
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
        reasoning = _extract_reasoning(delta)
        if reasoning:
            result["reasoning"] = reasoning
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
        if hasattr(chunk, "usage") and chunk.usage:
            result["usage"] = {
                "prompt_tokens": chunk.usage.prompt_tokens,
                "completion_tokens": chunk.usage.completion_tokens,
                "total_tokens": chunk.usage.total_tokens,
            }
        return result if result else None
