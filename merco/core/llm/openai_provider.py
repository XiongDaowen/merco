"""OpenAI-compatible ModelProvider transport."""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from typing import AsyncIterator, Optional

from merco.core.llm.base import ModelProvider
from merco.core.llm.errors import (
    AuthError,
    ConnectionError,
    ModelNotFoundError,
    ProviderError,
    RateLimitError,
)
from merco.core.llm.thinking import (
    _clean_content,
    _strip_think_tags,
    make_thinking_extractor,
)

logger = logging.getLogger("merco.llm.openai")

_SURROGATE_RE = re.compile(r'[\ud800-\udfff]')


def _clean_surrogates(obj):  # recursive surrogate cleaning
    if isinstance(obj, str):
        return _SURROGATE_RE.sub('', obj)
    if isinstance(obj, list):
        return [_clean_surrogates(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _clean_surrogates(v) for k, v in obj.items()}
    return obj


def _extract_usage(response) -> dict:  # OpenAI-only usage extraction
    usage = response.usage
    if not usage:
        return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    result = {
        "prompt_tokens": getattr(usage, "prompt_tokens", 0) or 0,
        "completion_tokens": getattr(usage, "completion_tokens", 0) or 0,
        "total_tokens": getattr(usage, "total_tokens", 0) or 0,
    }
    details = getattr(usage, "prompt_tokens_details", None)
    if details is not None:
        cd = getattr(details, "cached_tokens", None)
        if cd is not None:
            result["cached_tokens"] = cd
    return result


def translate_openai_error(exc: Exception) -> ProviderError:
    """Translate an openai SDK exception into a merco ProviderError subclass."""
    import openai
    status = getattr(exc, "status_code", None) or 0
    if isinstance(exc, openai.AuthenticationError):
        return AuthError(str(exc), status_code=status or 401)
    if isinstance(exc, openai.RateLimitError):
        return RateLimitError(str(exc), status_code=status or 429)
    if isinstance(exc, openai.APIConnectionError):
        return ConnectionError(str(exc), status_code=0)
    if isinstance(exc, openai.NotFoundError):
        return ModelNotFoundError(str(exc), status_code=status or 404)
    if isinstance(exc, openai.APIStatusError):
        return ProviderError(str(exc), status_code=status)
    return ProviderError(str(exc), status_code=status)


class OpenAICompatibleProvider(ModelProvider):
    """OpenAI-compatible transport. Covers openai/minimax/openrouter/deepseek."""

    name = "openai"

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4",
        base_url: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        cooldown: float = 0,
        extra_params: Optional[dict] = None,
        headers: Optional[dict] = None,
    ):
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.cooldown = cooldown
        self.extra_params = extra_params or {}
        self._last_request_time = 0.0
        self._client_ready = False
        self._extractor = make_thinking_extractor(model)

        import httpx
        from openai import AsyncOpenAI
        client_kwargs: dict = {
            "api_key": api_key,
            "max_retries": 0,
            "timeout": httpx.Timeout(connect=10.0, read=None, write=None, pool=10.0),
        }
        if base_url:
            client_kwargs["base_url"] = base_url
        if headers:
            client_kwargs["http_client"] = httpx.AsyncClient(headers=headers)
        self.client = AsyncOpenAI(**client_kwargs)

    async def chat(self, messages, tools=None, tool_choice="auto") -> dict:
        params = self._build_params(messages, tools, tool_choice)
        response = await self._request(params)
        return self._parse_response(response)

    async def chat_stream(self, messages, tools=None, tool_choice="auto") -> AsyncIterator[dict]:
        extractor = make_thinking_extractor(self.model)
        params = self._build_params(messages, tools, tool_choice, stream=True)
        stream = await self._request(params)
        async for chunk in stream:
            if parsed := self._parse_chunk(chunk, extractor):
                yield parsed

    def _build_params(self, messages, tools, tool_choice, stream=False) -> dict:
        # Streaming always requests usage in the final chunk (provider-internal,
        # not config-driven).
        params = {
            "model": self.model,
            "messages": _clean_surrogates(messages),
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        if stream:
            params["stream"] = True
            params["stream_options"] = {"include_usage": True}
        if tools:
            params["tools"] = tools
            params["tool_choice"] = tool_choice
        params.update(self.extra_params)
        return params

    async def _ensure_client_ready(self):
        if self._client_ready:
            return
        await asyncio.sleep(0)
        self._client_ready = True

    async def _request(self, params: dict):
        if self.cooldown > 0:
            elapsed = time.monotonic() - self._last_request_time
            if elapsed < self.cooldown:
                await asyncio.sleep(self.cooldown - elapsed)
        try:
            await self._ensure_client_ready()
            response = await self.client.chat.completions.create(**params)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            raise translate_openai_error(exc) from exc
        self._last_request_time = time.monotonic()
        return response

    @staticmethod
    def _normalize_tool_calls(tool_calls: list) -> list[dict]:
        result = []
        for tc in tool_calls:
            entry: dict = {
                "id": tc.id or "",
                "name": tc.function.name or "",
                "arguments": tc.function.arguments or "",
            }
            idx = getattr(tc, "index", None)
            if idx is not None:
                entry["index"] = idx
            result.append(entry)
        return result

    def _parse_response(self, response) -> dict:
        if not response.choices:
            return {"content": "", "finish_reason": None, "usage": _extract_usage(response)}
        choice = response.choices[0]
        message = choice.message
        content = message.content or ""
        usage_data = _extract_usage(response)
        result = {
            "role": message.role,
            "content": content,
            "reasoning": "",
            "finish_reason": choice.finish_reason,
            "usage": usage_data,
        }
        extracted = self._extractor.extract_from_message(message)
        if extracted:
            if extracted.get("reasoning"):
                result["reasoning"] = extracted["reasoning"]
            if "content" in extracted:
                result["content"] = extracted["content"] if extracted["content"] else ""
        result["content"] = _clean_content(result["content"])
        if message.tool_calls:
            normalized = self._normalize_tool_calls(message.tool_calls)
            result["tool_calls"] = [
                {**tc, "arguments": json.loads(tc["arguments"]) if tc["arguments"] else {}}
                for tc in normalized
            ]
        return result

    def _parse_chunk(self, chunk, extractor=None):
        choice = chunk.choices[0] if chunk.choices else None
        if not choice:
            return None
        delta = choice.delta
        if delta is None:
            return None
        result = {}
        ex = extractor if extractor is not None else make_thinking_extractor(self.model)
        extracted = ex.extract_from_delta(delta)
        if extracted.get("content"):
            result["content"] = _strip_think_tags(extracted["content"])
        if extracted.get("reasoning"):
            result["reasoning"] = _strip_think_tags(extracted["reasoning"])
        if delta.tool_calls:
            result["tool_calls"] = self._normalize_tool_calls(delta.tool_calls)
        if choice.finish_reason:
            result["finish_reason"] = choice.finish_reason
        if hasattr(chunk, "usage") and chunk.usage:
            result["usage"] = {
                "prompt_tokens": chunk.usage.prompt_tokens,
                "completion_tokens": chunk.usage.completion_tokens,
                "total_tokens": chunk.usage.total_tokens,
            }
        return result if result else None
