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
