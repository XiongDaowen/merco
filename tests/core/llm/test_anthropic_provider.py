"""AnthropicNativeProvider - native Messages API + translation."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from merco.core.llm.anthropic_provider import AnthropicNativeProvider
from merco.core.llm.errors import RateLimitError


def test_translate_tools_openai_to_anthropic():
    provider = AnthropicNativeProvider(api_key="k", model="claude-sonnet-4-20250514")
    openai_tools = [
        {
            "type": "function",
            "function": {
                "name": "search",
                "description": "d",
                "parameters": {"type": "object"},
            },
        }
    ]
    out = provider._translate_tools(openai_tools)
    assert out == [
        {
            "name": "search",
            "description": "d",
            "input_schema": {"type": "object"},
        }
    ]


def test_translate_messages_system_to_top_level():
    provider = AnthropicNativeProvider(api_key="k", model="claude-sonnet-4-20250514")
    msgs = [
        {"role": "system", "content": "be nice"},
        {"role": "user", "content": "hi"},
    ]
    system, translated = provider._translate_messages(msgs)
    assert system == "be nice"
    assert translated == [{"role": "user", "content": "hi"}]


def test_translate_messages_tool_result():
    provider = AnthropicNativeProvider(api_key="k", model="claude-sonnet-4-20250514")
    msgs = [{"role": "tool", "tool_call_id": "tc1", "content": "42"}]
    _system, translated = provider._translate_messages(msgs)
    assert translated == [
        {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "tc1",
                    "content": "42",
                }
            ],
        }
    ]


def test_translate_messages_assistant_tool_calls():
    provider = AnthropicNativeProvider(api_key="k", model="claude-sonnet-4-20250514")
    msgs = [
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "tc1",
                    "function": {"name": "search", "arguments": '{"q":"x"}'},
                }
            ],
        }
    ]
    _system, translated = provider._translate_messages(msgs)
    assert translated[0]["content"] == [
        {"type": "text", "text": ""},
        {
            "type": "tool_use",
            "id": "tc1",
            "name": "search",
            "input": {"q": "x"},
        },
    ]


def test_parse_response_blocks():
    provider = AnthropicNativeProvider(api_key="k", model="claude-sonnet-4-20250514")
    fake = MagicMock()
    fake.content = [
        SimpleNamespace(type="thinking", thinking="chain"),
        SimpleNamespace(type="text", text="answer"),
        SimpleNamespace(type="tool_use", id="tc1", name="search", input={"q": "x"}),
    ]
    fake.stop_reason = "end_turn"
    fake.usage = MagicMock(input_tokens=10, output_tokens=5)
    result = provider._parse_response(fake)
    assert result["content"] == "answer"
    assert result["reasoning"] == "chain"
    assert result["finish_reason"] == "stop"
    assert result["usage"]["prompt_tokens"] == 10
    assert result["tool_calls"][0]["function"]["name"] == "search"


def test_parse_response_extracts_cached_tokens():
    """Anthropic 缓存用量：从 cache_read_input_tokens 提取 cached_tokens。

    新架构下 Anthropic 用量提取住在 anthropic_provider._parse_response，仅吐
    cached_tokens（来自 cache_read_input_tokens）。旧 _client 的
    cache_read_tokens / cache_write_tokens 字段已废弃，不再断言。
    """
    provider = AnthropicNativeProvider(api_key="k", model="claude-sonnet-4-20250514")
    fake = MagicMock()
    fake.content = [SimpleNamespace(type="text", text="answer")]
    fake.stop_reason = "end_turn"
    fake.usage = MagicMock(
        input_tokens=100, output_tokens=20, cache_read_input_tokens=50
    )
    result = provider._parse_response(fake)
    assert result["usage"]["prompt_tokens"] == 100
    assert result["usage"]["completion_tokens"] == 20
    assert result["usage"]["total_tokens"] == 120
    assert result["usage"]["cached_tokens"] == 50


@pytest.mark.asyncio
async def test_chat_translates_rate_limit():
    import anthropic
    import httpx

    provider = AnthropicNativeProvider(api_key="k", model="claude-sonnet-4-20250514")
    provider.client = MagicMock()
    response = httpx.Response(
        429,
        request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"),
    )
    err = anthropic.RateLimitError("slow", response=response, body=None)
    provider.client.messages.create = AsyncMock(side_effect=err)
    with pytest.raises(RateLimitError):
        await provider.chat([{"role": "user", "content": "hi"}])
