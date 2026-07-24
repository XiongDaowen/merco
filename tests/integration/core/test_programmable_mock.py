"""ProgrammableModelProvider 与 Response DSL 单元测试"""

import pytest

from tests.integration.core.programmable_mock import ProgrammableModelProvider, Response


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


class TestProgrammableModelProvider:
    @pytest.mark.asyncio
    async def test_expect_returns_queued_responses(self):
        client = ProgrammableModelProvider()
        client.expect(
            [
                Response.content("first"),
                Response.content("second"),
            ]
        )

        r1 = await client.chat(messages=[])
        r2 = await client.chat(messages=[])
        assert r1["content"] == "first"
        assert r2["content"] == "second"

    @pytest.mark.asyncio
    async def test_expect_sequence_dynamic(self):
        client = ProgrammableModelProvider()
        client.expect_sequence(lambda i: Response.content(f"call_{i}"))

        r1 = await client.chat(messages=[])
        r2 = await client.chat(messages=[])
        r3 = await client.chat(messages=[])
        assert r1["content"] == "call_0"
        assert r2["content"] == "call_1"
        assert r3["content"] == "call_2"

    @pytest.mark.asyncio
    async def test_when_condition_routes(self):
        client = ProgrammableModelProvider()
        client.when(
            lambda msgs: "tool" in str(msgs),
            Response.content("with-tools"),
        )
        client.expect([Response.content("default")])

        r1 = await client.chat(messages=[{"role": "user", "content": "use a tool"}])
        r2 = await client.chat(messages=[{"role": "user", "content": "hello"}])
        assert r1["content"] == "with-tools"
        assert r2["content"] == "default"

    @pytest.mark.asyncio
    async def test_error_response_raises(self):
        client = ProgrammableModelProvider()
        client.expect([Response.error(RuntimeError("boom"))])

        with pytest.raises(RuntimeError, match="boom"):
            await client.chat(messages=[])

    @pytest.mark.asyncio
    async def test_tool_call_response_format(self):
        client = ProgrammableModelProvider()
        client.expect(
            [
                Response.tool_call("read_file", {"path": "/tmp/x"}),
            ]
        )

        r = await client.chat(messages=[])
        assert "tool_calls" in r
        assert r["tool_calls"][0]["name"] == "read_file"

    @pytest.mark.asyncio
    async def test_calls_recorded(self):
        client = ProgrammableModelProvider()
        client.expect([Response.content("x")])

        await client.chat(messages=[{"role": "user", "content": "hi"}])
        assert len(client.calls) == 1
        assert client.calls[0]["messages"][0]["content"] == "hi"

    @pytest.mark.asyncio
    async def test_empty_queue_raises(self):
        client = ProgrammableModelProvider()
        with pytest.raises(RuntimeError, match="no more responses"):
            await client.chat(messages=[])
