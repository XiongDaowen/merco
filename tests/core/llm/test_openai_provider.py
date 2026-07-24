"""OpenAICompatibleProvider transport tests."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from merco.core.llm.errors import RateLimitError
from merco.core.llm.openai_provider import (
    OpenAICompatibleProvider,
    _clean_surrogates,
    _extract_usage,
)


def _fake_choice(content="hi", finish="stop", tool_calls=None, reasoning=""):
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
    import httpx
    import openai

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
    ch = MagicMock()
    ch.delta = MagicMock(content="to", tool_calls=None)
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


# ── helpers for direct _parse_chunk / _parse_response tests ────────────────


def _fake_tool_call(id="call_1", name="bash", arguments=None, index=None):
    """Build a tool_call object with the .id / .function.{name,arguments} / .index
    shape that _normalize_tool_calls reads. index is only set when provided so
    getattr(tc, "index", None) returns None (matching a real tool_call without it)."""
    kwargs = {"id": id, "function": SimpleNamespace(name=name, arguments=arguments)}
    if index is not None:
        kwargs["index"] = index
    return SimpleNamespace(**kwargs)


def _fake_chunk(content=None, tool_calls=None, finish_reason=None, usage=None):
    """Build a streaming chunk with a single choice/delta."""
    delta = SimpleNamespace(content=content, tool_calls=tool_calls)
    choice = SimpleNamespace(delta=delta, finish_reason=finish_reason)
    return SimpleNamespace(choices=[choice], usage=usage)


# ── surrogate cleaning ───────────


class TestSurrogateCleaning:
    """代理对字符清理测试 - _clean_surrogates 现在住在 openai_provider.py。"""

    def test_clean_surrogates_string(self):
        """清理字符串中的孤立代理对（U+D800 高代理 / U+DC00 低代理单独出现均无效）。"""
        dirty = "Hello \ud800 World \udc00"
        clean = _clean_surrogates(dirty)
        assert clean == "Hello  World "

    def test_clean_surrogates_list(self):
        """清理列表中每个字符串的代理对。"""
        dirty = ["Hello \ud800", "World \udc00"]
        clean = _clean_surrogates(dirty)
        assert clean == ["Hello ", "World "]

    def test_clean_surrogates_dict(self):
        """递归清理字典值中的代理对。"""
        dirty = {"key1": "Hello \ud800", "key2": {"nested": "World \udc00"}}
        clean = _clean_surrogates(dirty)
        assert clean == {"key1": "Hello ", "key2": {"nested": "World "}}

    def test_clean_surrogates_no_change(self):
        """没有代理对的字符串（含合法 emoji / 中文）不被修改。"""
        original = "Hello World! 123 中文 🍺"
        clean = _clean_surrogates(original)
        assert clean == original


# ── usage extraction (OpenAI-only) ───


class TestUsageExtraction:
    """Token 用量提取测试 - _extract_usage 现在是 OpenAI-only，仅吐 cached_tokens。"""

    def test_extract_usage_basic(self):
        """基础用量提取。"""
        response = SimpleNamespace(usage=SimpleNamespace(prompt_tokens=100, completion_tokens=200, total_tokens=300))
        usage = _extract_usage(response)
        assert usage["prompt_tokens"] == 100
        assert usage["completion_tokens"] == 200
        assert usage["total_tokens"] == 300

    def test_extract_usage_none_usage(self):
        """usage 为 None 时返回零值。"""
        response = SimpleNamespace(usage=None)
        usage = _extract_usage(response)
        assert usage["prompt_tokens"] == 0
        assert usage["completion_tokens"] == 0
        assert usage["total_tokens"] == 0

    def test_extract_usage_openai_cache(self):
        """OpenAI 缓存用量：从 prompt_tokens_details.cached_tokens 提取 cached_tokens。"""
        response = SimpleNamespace(
            usage=SimpleNamespace(
                prompt_tokens=100,
                completion_tokens=200,
                total_tokens=300,
                prompt_tokens_details=SimpleNamespace(cached_tokens=75),
            )
        )
        usage = _extract_usage(response)
        assert usage["cached_tokens"] == 75


# ── _parse_chunk edge cases ────────────────────


def test_parse_chunk_handles_none_arguments():
    """_parse_chunk 处理 tool_call 首 chunk 的 arguments=None 时不抛 TypeError，落地为 ""。"""
    provider = OpenAICompatibleProvider(api_key="k", model="gpt-4o")
    tc = _fake_tool_call(id="call_123", name="bash", arguments=None, index=0)
    chunk = _fake_chunk(content=None, tool_calls=[tc])
    result = provider._parse_chunk(chunk)
    assert result is not None
    assert "tool_calls" in result
    parsed = result["tool_calls"][0]
    assert parsed["id"] == "call_123"
    assert parsed["name"] == "bash"
    assert parsed["arguments"] == ""  # None -> "" (chunk path does NOT json.loads)
    assert parsed["index"] == 0


def test_parse_chunk_handles_none_id_and_name():
    """_parse_chunk 中 tc.id / tc.function.name 为 None 时安全落地为 ""。"""
    provider = OpenAICompatibleProvider(api_key="k", model="gpt-4o")
    tc = _fake_tool_call(id=None, name=None, arguments="ls -la", index=0)
    chunk = _fake_chunk(content="", tool_calls=[tc])
    result = provider._parse_chunk(chunk)
    assert result is not None
    parsed = result["tool_calls"][0]
    assert parsed["id"] == ""
    assert parsed["name"] == ""
    assert parsed["arguments"] == "ls -la"


# ── _parse_response edge cases ─────────────────


def test_parse_response_handles_empty_choices():
    """_parse_response 中 response.choices 为空时不抛 IndexError，返回空 content + None finish。"""
    provider = OpenAICompatibleProvider(api_key="k", model="gpt-4o")
    response = SimpleNamespace(choices=[], usage=None)
    result = provider._parse_response(response)
    assert result["content"] == ""
    assert result["finish_reason"] is None


def test_parse_response_handles_none_arguments():
    """_parse_response 中 tc.function.arguments=None 时安全落地为 {}（json.loads 仅对非空串执行）。"""
    provider = OpenAICompatibleProvider(api_key="k", model="gpt-4o")
    tc = _fake_tool_call(id="call_456", name="bash", arguments=None)
    response = _fake_choice(content="", finish="tool_calls", tool_calls=[tc])
    result = provider._parse_response(response)
    assert "tool_calls" in result
    parsed = result["tool_calls"][0]
    assert parsed["id"] == "call_456"
    assert parsed["name"] == "bash"
    assert parsed["arguments"] == {}  # None -> "" -> falsy -> {}


@pytest.mark.asyncio
async def test_chat_parses_tool_calls():
    """chat() 返回的 tool_calls 是 FLAT dict（{id, name, arguments, index?}），
    没有 function 包装；arguments 被 json.loads 成 dict。

    注意：旧 plan 示例断言 result["tool_calls"][0]["function"]["arguments"] 是错的——
    规范化后是扁平结构（见 _normalize_tool_calls / _parse_response）。
    """
    provider = OpenAICompatibleProvider(api_key="k", model="gpt-4o")
    tc = _fake_tool_call(id="tc1", name="search", arguments='{"q":"x"}', index=0)
    resp = _fake_choice(content="", finish="tool_calls", tool_calls=[tc])
    provider.client = MagicMock()
    provider.client.chat.completions.create = AsyncMock(return_value=resp)
    result = await provider.chat([{"role": "user", "content": "hi"}])
    assert result["tool_calls"][0]["id"] == "tc1"
    assert result["tool_calls"][0]["name"] == "search"
    assert result["tool_calls"][0]["arguments"] == {"q": "x"}
    assert result["tool_calls"][0]["index"] == 0
    assert "function" not in result["tool_calls"][0]
