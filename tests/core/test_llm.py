"""LLM 客户端单元测试"""

import json
from merco.core.llm import LLMClient


def test_parse_chunk_handles_none_arguments():
    """_parse_chunk 处理 tool_call 首 chunk 的 arguments=None 时不抛 TypeError。"""
    class FakeFunction:
        name = "bash"
        arguments = None

    class FakeToolCall:
        index = 0
        id = "call_123"
        function = FakeFunction()

    class FakeDelta:
        tool_calls = [FakeToolCall()]
        content = None

    class FakeChoice:
        delta = FakeDelta()
        finish_reason = None

    class FakeChunk:
        choices = [FakeChoice()]
        usage = None

    client = LLMClient(api_key="test", base_url="http://test")
    result = client._parse_chunk(FakeChunk())

    assert result is not None
    assert "tool_calls" in result
    assert result["tool_calls"][0]["arguments"] == ""


def test_parse_chunk_handles_none_id_and_name():
    """_parse_chunk 中 tc.id / tc.function.name 为 None 时安全落地。"""
    class FakeFunction:
        name = None
        arguments = "ls -la"

    class FakeToolCall:
        index = 0
        id = None
        function = FakeFunction()

    class FakeDelta:
        tool_calls = [FakeToolCall()]
        content = ""

    class FakeChoice:
        delta = FakeDelta()
        finish_reason = None

    class FakeChunk:
        choices = [FakeChoice()]
        usage = None

    client = LLMClient(api_key="test", base_url="http://test")
    result = client._parse_chunk(FakeChunk())

    assert result is not None
    tc = result["tool_calls"][0]
    assert tc["id"] == ""
    assert tc["name"] == ""
    assert tc["arguments"] == "ls -la"


def test_parse_response_handles_empty_choices():
    """_parse_response 中 response.choices 为空时不抛 IndexError。"""
    class FakeResponse:
        choices = []

        class Usage:
            prompt_tokens = 0
            completion_tokens = 0
            total_tokens = 0
        usage = Usage()

    client = LLMClient(api_key="test", base_url="http://test")
    result = client._parse_response(FakeResponse())

    assert result["content"] == ""
    assert result["finish_reason"] is None


def test_parse_response_handles_none_arguments():
    """_parse_response 中 tc.function.arguments 为 None 时安全落地为 {}。"""
    class FakeFunction:
        name = "bash"
        arguments = None

    class FakeToolCall:
        id = "call_456"
        function = FakeFunction()

    class FakeMessage:
        content = ""
        role = "assistant"
        tool_calls = [FakeToolCall()]

    class FakeChoice:
        message = FakeMessage()
        finish_reason = "tool_calls"

    class FakeResponse:
        choices = [FakeChoice()]
        usage = None

    client = LLMClient(api_key="test", base_url="http://test")
    result = client._parse_response(FakeResponse())

    assert "tool_calls" in result
    tc = result["tool_calls"][0]
    assert tc["id"] == "call_456"
    assert tc["name"] == "bash"
    assert tc["arguments"] == {}


def test_strip_think_tags_preserves_internal_whitespace():
    """回归测试：_strip_think_tags 在流式场景下不应破坏词边界。
    旧实现末尾 .strip() 会去掉每 chunk 的首尾空白，拼接后空格消失。
    """
    from merco.core.llm import _strip_think_tags, _clean_content

    # 模拟流式 chunk
    chunks = ["hello ", "world", " how ", "are you"]
    buf = ""
    for c in chunks:
        buf += _strip_think_tags(c)
    assert buf == "hello world how are you", f"spaces lost: {buf!r}"

    # think 块（标准闭合）正常剥离
    assert _strip_think_tags("<think>hi</think>hello world") == "hello world"
    assert _strip_think_tags("a<think>b</think>c") == "ac"
    # 多行 think 块也能剥离（DOTALL 已加）
    assert _strip_think_tags("<think>line1\nline2</think>after") == "after"
    # 前后空白保留（chunk 安全）
    assert _strip_think_tags("  hello  ") == "  hello  "


def test_clean_content_strips_think_tags_and_outer_whitespace():
    """_clean_content 是非流式终态处理：去标签 + strip 前后空白。"""
    from merco.core.llm import _clean_content

    assert _clean_content("  hello world  ") == "hello world"
    assert _clean_content("<think>thinking</think>real content") == "real content"
    assert _clean_content("<think>t1</think> middle <think>t2</think>") == "middle"
