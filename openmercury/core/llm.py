"""LLM 客户端 - OpenAI 兼容接口"""
import json
import logging
import re
import time
import asyncio
from typing import Any, Optional, AsyncIterator
from openai import AsyncOpenAI, APIStatusError


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


class LLMClient:
    """OpenAI 兼容的 LLM 客户端"""

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4",
        base_url: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        retry_delays: tuple = (2, 4),  # 429/5xx 退避间隔（秒），空元组禁用重试
        cooldown: float = 0,  # 请求最小间隔（秒），0=不禁用；频控严格的网关设为 5-10
    ):
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.retry_delays = retry_delays
        self.cooldown = cooldown
        self._last_request_time = 0.0

        client_kwargs = {
            "api_key": api_key,
            "max_retries": 0,  # 关闭 SDK 自动重试，改用统一退避策略
        }
        if base_url:
            client_kwargs["base_url"] = base_url

        self.client = AsyncOpenAI(**client_kwargs)

    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] = None,
        tool_choice: str | dict[str, Any] = "auto",
    ) -> dict:
        """发送聊天请求并获取响应"""

        params = {
            "model": self.model,
            "messages": _clean_surrogates(messages),
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }

        if tools:
            params["tools"] = tools
            params["tool_choice"] = tool_choice

        logger.debug("→ API 请求: model=%s messages=%d tools=%d", 
                     self.model, len(params["messages"]), len(tools or []))

        # 请求间隔冷却：防止频繁请求触发网关频控
        if self.cooldown > 0:
            elapsed = time.monotonic() - self._last_request_time
            if elapsed < self.cooldown:
                wait = self.cooldown - elapsed
                logger.debug("⏳ 冷却 %.1fs（距上次请求 %.1fs）", wait, elapsed)
                await asyncio.sleep(wait)

        # 统一重试策略：429 和 5xx 均可重试，4xx 不重试
        max_retries = len(self.retry_delays)
        for attempt in range(max_retries + 1):
            try:
                response = await self.client.chat.completions.create(**params)
                self._last_request_time = time.monotonic()
                break
            except APIStatusError as e:
                status = e.status_code
                retryable = status == 429 or status >= 500
                if retryable and attempt < max_retries:
                    delay = self.retry_delays[attempt]
                    logger.warning("⚠ HTTP %d，%ds 后重试 (%d/%d)", status, delay, attempt + 1, max_retries)
                    await asyncio.sleep(delay)
                else:
                    logger.error("✗ API 错误: HTTP %d - %s", status, str(e))
                    logger.error("  请求体大小: %d 字符", len(json.dumps(params, ensure_ascii=True)))
                    raise
            except Exception as e:
                # 非 HTTP 错误（网络/序列化等），不重试
                logger.error("✗ 请求失败: %s - %s", type(e).__name__, str(e))
                raise

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

        params = {
            "model": self.model,
            "messages": _clean_surrogates(messages),
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": True,
        }

        if tools:
            params["tools"] = tools
            params["tool_choice"] = tool_choice

        # 请求间隔冷却
        if self.cooldown > 0:
            elapsed = time.monotonic() - self._last_request_time
            if elapsed < self.cooldown:
                wait = self.cooldown - elapsed
                await asyncio.sleep(wait)

        # 统一重试策略：429 和 5xx 均可重试，4xx 不重试
        stream = None
        max_retries = len(self.retry_delays)
        for attempt in range(max_retries + 1):
            try:
                stream = await self.client.chat.completions.create(**params)
                break
            except APIStatusError as e:
                status = e.status_code
                retryable = status == 429 or status >= 500
                if retryable and attempt < max_retries:
                    delay = self.retry_delays[attempt]
                    logger.warning("⚠ HTTP %d(stream)，%ds 后重试 (%d/%d)", status, delay, attempt + 1, max_retries)
                    await asyncio.sleep(delay)
                else:
                    raise
            except Exception:
                raise

        assert stream is not None
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
