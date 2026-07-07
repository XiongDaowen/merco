"""ProgrammableLLMClient 与 Response DSL 单元测试"""
import pytest
from tests.integration.core.programmable_mock import Response


class TestResponseDSL:
    def test_content_factory(self):
        r = Response.content("hello")
        assert r.content == "hello"
        assert r.tool_calls == []
        assert r.error is None
        assert r.delay == 0.0

    def test_tool_call_factory(self):
        r = Response.tool_call("read_file", {"path": "/tmp/x"})
        assert r.content == ""
        assert len(r.tool_calls) == 1
        assert r.tool_calls[0] == {
            "id": "manual_0",
            "name": "read_file",
            "arguments": {"path": "/tmp/x"},
        }

    def test_error_factory(self):
        exc = RuntimeError("boom")
        r = Response.error(exc)
        assert r.error is exc
        assert r.content == ""

    def test_tool_call_with_explicit_id(self):
        r = Response.tool_call("bash", {"command": "ls"}, id="call_123")
        assert r.tool_calls[0]["id"] == "call_123"

    def test_delay_default_zero(self):
        r = Response.content("x")
        assert r.delay == 0.0
