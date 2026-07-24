"""Integration tests: AnthropicNativeProvider driving the agent loop with tools.

These prove Wave 2's goal - a non-OpenAI provider executes tool calls end-to-end
through the agent loop. They guard against two regressions:

* Test A (non-streaming): the provider's ``_parse_response`` must emit FLAT
  ``{id, name, arguments}`` tool_calls (merco's internal contract). The agent
  loop reads ``tc["name"]`` directly; a nested OpenAI-wire-shaped block crashes
  with ``KeyError: 'name'`` at agent.py:538.
* Test B (streaming): ``_parse_stream_event`` must handle ``content_block_start``
  (where Anthropic delivers tool_use id/name) and use ``event.index``. Otherwise
  StreamingProvider assembles empty id/name and the agent silently drops the call.

The mock SDK surface mirrors how ``tests/core/llm/test_anthropic_provider.py``
mocks ``provider.client.messages`` and how ``tests/integration/test_stream_scenarios.py``
mocks streaming providers.
"""

from io import StringIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from merco.core.agent import Agent
from merco.core.config import MercoConfig, StreamingConfig
from merco.core.llm.anthropic_provider import AnthropicNativeProvider
from merco.tools.base import BaseTool
from merco.tools.registry import ToolRegistry

# ── Recording test tool ──────────────────────────────────────────────


class SearchTool(BaseTool):
    """A tool the mocked Anthropic response will ask to call.

    Records every invocation so the test can assert the agent actually
    dispatched the tool call with the right arguments.
    """

    name = "search"
    description = "search for something"
    toolset = "test"
    parameters = {
        "type": "object",
        "properties": {"q": {"type": "string"}},
        "required": ["q"],
    }

    def __init__(self):
        self.calls: list[dict] = []

    async def execute(self, q: str, **kwargs):
        self.calls.append({"q": q})
        return {"results": [f"hit for {q}"]}


# ── Helpers ──────────────────────────────────────────────────────────


def _quiet_console(monkeypatch):
    """Redirect the agent module's rich Console to a StringIO buffer."""
    from rich.console import Console

    quiet = Console(file=StringIO(), force_terminal=True, width=120)
    monkeypatch.setattr("merco.core.agent.console", quiet)
    return quiet


def _make_tool_registry() -> ToolRegistry:
    reg = ToolRegistry()
    reg.register(SearchTool())
    return reg


def _tool_use_response() -> SimpleNamespace:
    """Anthropic Messages API response carrying one tool_use block."""
    return SimpleNamespace(
        content=[
            SimpleNamespace(type="text", text="calling tool"),
            SimpleNamespace(type="tool_use", id="tc1", name="search", input={"q": "x"}),
        ],
        stop_reason="tool_use",
        usage=SimpleNamespace(input_tokens=5, output_tokens=5),
    )


def _final_text_response() -> SimpleNamespace:
    """Anthropic Messages API response with plain text (terminates the loop)."""
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text="done")],
        stop_reason="end_turn",
        usage=SimpleNamespace(input_tokens=5, output_tokens=5),
    )


def _build_agent(monkeypatch, tmp_path, *, streaming: bool) -> tuple[Agent, SearchTool]:
    """Construct an Agent wired to a (mocked) AnthropicNativeProvider."""
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr("merco.core.agent._get_db_path", lambda: db_path)

    cfg = MercoConfig()
    cfg.model.api_key = "test-key"
    cfg.model.model = "claude-sonnet-4-20250514"
    cfg.sandbox_mode = "auto"
    cfg.memory_path = str(tmp_path / "memory")
    if streaming:
        cfg.streaming = StreamingConfig(enabled=True, content=True, think=True)

    search = SearchTool()
    reg = ToolRegistry()
    reg.register(search)
    agent = Agent(config=cfg, tool_registry=reg)

    provider = AnthropicNativeProvider(api_key="k", model="claude-sonnet-4-20250514")
    agent.provider = provider
    return agent, search


# ── Test A: non-streaming Anthropic tool call through the agent loop ─


@pytest.mark.asyncio
async def test_anthropic_non_streaming_tool_call_through_agent_loop(monkeypatch, tmp_path):
    """A non-streaming Anthropic tool_use block must drive the agent loop.

    Before the C1 fix, _parse_response emitted nested {id,type,function:{...}}
    and agent.py:538 (a logger.debug list-comprehension, eagerly evaluated)
    raised KeyError: 'name'.
    """
    _quiet_console(monkeypatch)
    agent, search = _build_agent(monkeypatch, tmp_path, streaming=False)

    agent.provider.client.messages.create = AsyncMock(side_effect=[_tool_use_response(), _final_text_response()])

    result = await agent.run("search for x")

    # The search tool must have been dispatched with the parsed arguments.
    assert search.calls == [{"q": "x"}], (
        f"search tool should have been called once with {{'q':'x'}}, got {search.calls}"
    )
    # And the loop must have terminated with the final text response.
    assert "done" in result


# ── Test B: streaming Anthropic tool call through the agent loop ─────


class _FakeAnthropicStream:
    """Async context manager double for anthropic's stream manager.

    Yields the supplied events via ``async for`` and returns ``final`` from
    ``get_final_message()`` - the two surfaces ``chat_stream`` touches.
    """

    def __init__(self, events: list, final: SimpleNamespace):
        self._events = list(events)
        self._final = final
        self._idx = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._idx >= len(self._events):
            raise StopAsyncIteration
        ev = self._events[self._idx]
        self._idx += 1
        return ev

    async def get_final_message(self):
        return self._final


def _tool_use_stream_events() -> list:
    """Anthropic stream events for one tool_use block at index 0."""
    return [
        SimpleNamespace(
            type="content_block_start",
            index=0,
            content_block=SimpleNamespace(type="tool_use", id="tc1", name="search", input={}),
        ),
        SimpleNamespace(
            type="content_block_delta",
            index=0,
            delta=SimpleNamespace(type="input_json_delta", partial_json='{"q":"x"}'),
        ),
        SimpleNamespace(type="content_block_stop", index=0),
    ]


def _final_text_stream_events() -> list:
    """Anthropic stream events for a plain text block at index 0."""
    return [
        SimpleNamespace(
            type="content_block_start",
            index=0,
            content_block=SimpleNamespace(type="text", text=""),
        ),
        SimpleNamespace(
            type="content_block_delta",
            index=0,
            delta=SimpleNamespace(type="text_delta", text="done"),
        ),
        SimpleNamespace(type="content_block_stop", index=0),
    ]


@pytest.mark.asyncio
async def test_anthropic_streaming_tool_call_through_agent_loop(monkeypatch, tmp_path):
    """A streaming Anthropic tool_use must drive the agent loop.

    Before the I1 fix, _parse_stream_event never handled content_block_start
    (where id/name arrive) and hardcoded index 0. StreamingProvider assembled
    {id:"",name:"",arguments:{...}}; agent.py:575 then filtered it out as a
    hallucination, so the tool was silently never called.
    """
    _quiet_console(monkeypatch)
    agent, search = _build_agent(monkeypatch, tmp_path, streaming=True)

    call_count = [0]

    def _stream_factory(**params):
        call_count[0] += 1
        if call_count[0] == 1:
            return _FakeAnthropicStream(
                _tool_use_stream_events(),
                SimpleNamespace(
                    stop_reason="tool_use",
                    usage=SimpleNamespace(input_tokens=5, output_tokens=5),
                ),
            )
        return _FakeAnthropicStream(
            _final_text_stream_events(),
            SimpleNamespace(
                stop_reason="end_turn",
                usage=SimpleNamespace(input_tokens=5, output_tokens=5),
            ),
        )

    agent.provider.client.messages.stream = MagicMock(side_effect=_stream_factory)

    result = await agent.run("search for x")

    assert search.calls == [{"q": "x"}], (
        f"search tool should have been called once with {{'q':'x'}}, got {search.calls}"
    )
    assert "done" in result
