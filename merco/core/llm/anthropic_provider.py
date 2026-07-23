"""AnthropicNativeProvider - real Messages API.

Proves the ModelProvider ABC is not OpenAI-shaped: translates OpenAI-format
messages/tools to Anthropic wire format, reads native thinking/tool_use blocks,
streams via the SDK stream manager.
"""

from __future__ import annotations

import json
import logging
from typing import Any, AsyncIterator

from merco.core.llm.base import ModelProvider
from merco.core.llm.errors import (
    AuthError,
    ConnectionError,
    ModelNotFoundError,
    ProviderError,
    RateLimitError,
)

logger = logging.getLogger("merco.llm.anthropic")

_STOP_REASON_MAP = {
    "end_turn": "stop",
    "tool_use": "tool_calls",
    "max_tokens": "length",
}


def translate_anthropic_error(exc: Exception) -> ProviderError:
    """Translate an anthropic SDK exception into a merco ProviderError subclass."""
    import anthropic
    status = getattr(exc, "status_code", None) or 0
    if isinstance(exc, getattr(anthropic, "AuthenticationError", type(None))):
        return AuthError(str(exc), status_code=status or 401)
    if isinstance(exc, getattr(anthropic, "RateLimitError", type(None))):
        return RateLimitError(str(exc), status_code=status or 429)
    if isinstance(exc, getattr(anthropic, "APIConnectionError", type(None))):
        return ConnectionError(str(exc), status_code=0)
    if isinstance(exc, getattr(anthropic, "NotFoundError", type(None))):
        return ModelNotFoundError(str(exc), status_code=status or 404)
    if isinstance(exc, getattr(anthropic, "APIStatusError", type(None))):
        return ProviderError(str(exc), status_code=status)
    return ProviderError(str(exc), status_code=status)


class AnthropicNativeProvider(ModelProvider):
    """Native Anthropic Messages API transport."""

    name = "anthropic"

    def __init__(
        self,
        api_key: str,
        model: str = "claude-sonnet-4-20250514",
        base_url: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        cooldown: float = 0,
        extra_params: dict | None = None,
        headers: dict | None = None,
    ):
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.cooldown = cooldown
        self.extra_params = extra_params or {}
        self._extra_headers = headers or {}

        from anthropic import AsyncAnthropic

        kwargs: dict[str, Any] = {"api_key": api_key, "max_retries": 0}
        if base_url:
            kwargs["base_url"] = base_url
        if self._extra_headers:
            kwargs["default_headers"] = self._extra_headers
        self.client = AsyncAnthropic(**kwargs)

    def _translate_tools(self, tools: list[dict]) -> list[dict]:
        out = []
        for tool in tools:
            function = tool.get("function", tool)
            out.append(
                {
                    "name": function["name"],
                    "description": function.get("description", ""),
                    "input_schema": function.get("parameters", {"type": "object"}),
                }
            )
        return out

    def _translate_messages(self, messages: list[dict]) -> tuple[str, list[dict]]:
        """Return top-level system text and Anthropic-shaped messages."""
        system_parts: list[str] = []
        translated: list[dict] = []
        for message in messages:
            role = message.get("role")
            if role == "system":
                system_parts.append(message.get("content", ""))
                continue
            if role == "tool":
                translated.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": message.get("tool_call_id", ""),
                                "content": message.get("content", ""),
                            }
                        ],
                    }
                )
                continue
            if role == "assistant" and message.get("tool_calls"):
                blocks: list[dict] = [
                    {"type": "text", "text": message.get("content", "")}
                ]
                for tool_call in message["tool_calls"]:
                    function = tool_call.get("function", {})
                    arguments = function.get("arguments", "{}")
                    try:
                        parsed = json.loads(arguments) if isinstance(arguments, str) else arguments
                    except json.JSONDecodeError:
                        parsed = {}
                    blocks.append(
                        {
                            "type": "tool_use",
                            "id": tool_call.get("id", ""),
                            "name": function.get("name", ""),
                            "input": parsed,
                        }
                    )
                translated.append({"role": "assistant", "content": blocks})
                continue
            translated.append({"role": role, "content": message.get("content", "")})
        return "\n\n".join(system_parts), translated

    def _build_params(self, messages, tools, tool_choice):
        system, translated = self._translate_messages(messages)
        params: dict[str, Any] = {
            "model": self.model,
            "messages": translated,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
        }
        if system:
            params["system"] = system
        if tools:
            params["tools"] = self._translate_tools(tools)
            if tool_choice == "auto":
                params["tool_choice"] = {"type": "auto"}
            elif tool_choice == "none":
                params["tool_choice"] = {"type": "none"}
            elif isinstance(tool_choice, dict):
                params["tool_choice"] = tool_choice
        params.update(self.extra_params)
        return params

    def _parse_response(self, response) -> dict:
        content = ""
        reasoning = ""
        tool_calls: list[dict] = []
        for block in response.content or []:
            block_type = getattr(block, "type", None)
            if block_type == "text":
                content += getattr(block, "text", "") or ""
            elif block_type == "thinking":
                reasoning += getattr(block, "thinking", "") or ""
            elif block_type == "tool_use":
                tool_calls.append(
                    {
                        "id": getattr(block, "id", ""),
                        "name": getattr(block, "name", ""),
                        "arguments": getattr(block, "input", {}) or {},
                    }
                )
        usage = response.usage
        input_tokens = getattr(usage, "input_tokens", 0) or 0
        output_tokens = getattr(usage, "output_tokens", 0) or 0
        usage_dict = {
            "prompt_tokens": input_tokens,
            "completion_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
        }
        cached = getattr(usage, "cache_read_input_tokens", None)
        if cached is not None:
            usage_dict["cached_tokens"] = cached
        return {
            "role": "assistant",
            "content": content,
            "reasoning": reasoning,
            "finish_reason": _STOP_REASON_MAP.get(
                getattr(response, "stop_reason", ""), "stop"
            ),
            "usage": usage_dict,
            **({"tool_calls": tool_calls} if tool_calls else {}),
        }

    async def chat(self, messages, tools=None, tool_choice="auto") -> dict:
        params = self._build_params(messages, tools, tool_choice)
        try:
            response = await self.client.messages.create(**params)
        except Exception as exc:
            raise translate_anthropic_error(exc) from exc
        return self._parse_response(response)

    async def chat_stream(
        self, messages, tools=None, tool_choice="auto"
    ) -> AsyncIterator[dict]:
        params = self._build_params(messages, tools, tool_choice)
        params["stream"] = True
        try:
            async with self.client.messages.stream(**params) as stream:
                async for event in stream:
                    parsed = self._parse_stream_event(event)
                    if parsed:
                        yield parsed
                final = await stream.get_final_message()
                yield self._final_chunk(final)
        except Exception as exc:
            raise translate_anthropic_error(exc) from exc

    def _parse_stream_event(self, event) -> dict | None:
        event_type = getattr(event, "type", None)
        if event_type == "content_block_start":
            block = getattr(event, "content_block", None)
            if block is not None and getattr(block, "type", None) == "tool_use":
                return {
                    "tool_calls": [
                        {
                            "index": getattr(event, "index", 0),
                            "id": getattr(block, "id", ""),
                            "name": getattr(block, "name", ""),
                        }
                    ]
                }
            return None
        if event_type != "content_block_delta":
            return None
        delta = event.delta
        delta_type = getattr(delta, "type", None)
        if delta_type == "text_delta":
            return {"content": getattr(delta, "text", "")}
        if delta_type == "thinking_delta":
            return {"reasoning": getattr(delta, "thinking", "")}
        if delta_type == "input_json_delta":
            return {
                "tool_calls": [
                    {
                        "index": getattr(event, "index", 0),
                        "arguments": getattr(delta, "partial_json", ""),
                    }
                ]
            }
        return None

    def _final_chunk(self, final) -> dict:
        chunk: dict[str, Any] = {
            "finish_reason": _STOP_REASON_MAP.get(
                getattr(final, "stop_reason", ""), "stop"
            )
        }
        usage = final.usage
        if usage:
            input_tokens = getattr(usage, "input_tokens", 0) or 0
            output_tokens = getattr(usage, "output_tokens", 0) or 0
            chunk["usage"] = {
                "prompt_tokens": input_tokens,
                "completion_tokens": output_tokens,
                "total_tokens": input_tokens + output_tokens,
            }
        return chunk
