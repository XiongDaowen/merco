"""OpenAICompatibleProvider - absorbs LLMClient transport."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from merco.core.llm.openai_provider import OpenAICompatibleProvider
from merco.core.llm.errors import ProviderError, RateLimitError


def _fake_choice(content="hi", finish="stop", tool_calls=None, reasoning=""):
    delta = MagicMock()
    message = MagicMock()
    message.role = "assistant"
    message.content = content
    message.tool_calls = tool_calls
    message.model_extra = {"reasoning_content": reasoning} if reasoning else {}
    choice = MagicMock()
    choice.message = message
    choice.finish_reason = finish
    resp = MagicMock()
    resp.choices = [choice]
    resp.usage = None
    return resp


@pytest.mark.asyncio
async def test_chat_returns_normalized_dict():
    provider = OpenAICompatibleProvider(api_key="k", model="gpt-4o")
    fake_resp = _fake_choice(content="hello", finish="stop")
    provider.client = MagicMock()
    provider.client.chat.completions.create = AsyncMock(return_value=fake_resp)
    result = await provider.chat([{"role": "user", "content": "hi"}])
    assert result["role"] == "assistant"
    assert result["content"] == "hello"
    assert result["finish_reason"] == "stop"
    assert result["reasoning"] == ""


@pytest.mark.asyncio
async def test_chat_translates_rate_limit_to_provider_error():
    import openai, httpx
    provider = OpenAICompatibleProvider(api_key="k", model="gpt-4o")
    provider.client = MagicMock()
    req = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
    resp = httpx.Response(429, request=req)
    err = openai.RateLimitError("slow down", response=resp, body=None)
    provider.client.chat.completions.create = AsyncMock(side_effect=err)
    with pytest.raises(RateLimitError) as ei:
        await provider.chat([{"role": "user", "content": "hi"}])
    assert ei.value.status_code == 429


@pytest.mark.asyncio
async def test_chat_stream_yields_chunks():
    provider = OpenAICompatibleProvider(api_key="k", model="gpt-4o")
    chunk = MagicMock()
    ch = MagicMock(); ch.delta = MagicMock(content="to", tool_calls=None)
    ch.delta.model_extra = {}
    ch.finish_reason = None
    chunk.choices = [ch]
    chunk.usage = None
    provider.client = MagicMock()
    async def _async_iter(items):
        for x in items:
            yield x
    provider.client.chat.completions.create = AsyncMock(return_value=_async_iter([chunk]))
    out = []
    async for c in provider.chat_stream([{"role": "user", "content": "hi"}]):
        out.append(c)
    assert out and out[0]["content"] == "to"