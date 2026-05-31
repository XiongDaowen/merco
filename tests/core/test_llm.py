"""LLM 客户端单元测试"""

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
