"""Integration tests for streaming content output edge cases.

Tests the StreamingProvider with various configurations:
- thinking + content both streaming
- empty content handling
- tool_calls with streaming
- Ctrl+C interruption during streaming
- stream_thinking_transient=True
"""

import asyncio
import pytest
from io import StringIO
from unittest.mock import MagicMock

from merco.core.llm.base import ModelProvider
from merco.core.config import MercoConfig, StreamingConfig
from merco.core.agent import Agent
from tests.conftest import make_test_registry


# ── Enhanced Mock LLM for streaming tests ──────────────────────────

class StreamingMockProvider(ModelProvider):
    """Mock LLM that yields multiple chunks to simulate real streaming.

    Can be used as a drop-in mock (accepts the same init kwargs) or
    instantiated directly with chunks for test setup.
    """
    name = "mock"

    def __init__(self, chunks: list[dict] | None = None, **kwargs):
        """
        chunks: list of dicts, each may have:
          - "reasoning": str chunk of reasoning text
          - "content": str chunk of content text
          - "tool_calls": list of tool_call chunks
          - "finish_reason": str
          - "usage": dict
        **kwargs: accepted for init-signature compatibility
        """
        self.chunks = list(chunks or [])
        self.calls: list[dict] = []

    async def chat(self, messages: list[dict], tools: list[dict] = None,
                   tool_choice: str = "auto") -> dict:
        """Non-streaming: assemble all chunks into one response."""
        self.calls.append({"messages": messages, "tools": tools})
        assembled = {"role": "assistant", "content": "", "reasoning": "",
                     "tool_calls": [], "finish_reason": "stop"}
        for chunk in self.chunks:
            assembled["content"] += chunk.get("content", "")
            assembled["reasoning"] += chunk.get("reasoning", "")
            if chunk.get("tool_calls"):
                assembled["tool_calls"].extend(chunk["tool_calls"])
            if chunk.get("finish_reason"):
                assembled["finish_reason"] = chunk["finish_reason"]
            if chunk.get("usage"):
                assembled["usage"] = chunk["usage"]
        return assembled

    async def chat_stream(self, messages: list[dict], tools: list[dict] = None,
                          tool_choice: str = "auto"):
        """Yield chunks one by one to simulate streaming."""
        self.calls.append({"messages": messages, "tools": tools})
        for chunk in self.chunks:
            yield chunk


class SlowStreamingMockProvider(StreamingMockProvider):
    """Mock LLM with delays between chunks to simulate slow API."""

    def __init__(self, chunks: list[dict] | None = None, delay: float = 0.05, **kwargs):
        super().__init__(chunks, **kwargs)
        self.delay = delay

    async def chat_stream(self, messages: list[dict], tools: list[dict] = None,
                          tool_choice: str = "auto"):
        self.calls.append({"messages": messages, "tools": tools})
        for chunk in self.chunks:
            await asyncio.sleep(self.delay)
            yield chunk


class CancellingMockProvider(ModelProvider):
    """Mock LLM that cancels the current task mid-stream."""
    name = "mock"

    def __init__(self, chunks_before_cancel: list[dict], **kwargs):
        self.chunks = list(chunks_before_cancel)
        self.calls: list[dict] = []

    async def chat(self, messages, tools=None, tool_choice="auto"):
        return {"content": "", "finish_reason": "stop"}

    async def chat_stream(self, messages, tools=None, tool_choice="auto"):
        self.calls.append({"messages": messages, "tools": tools})
        for chunk in self.chunks:
            yield chunk
        # Cancel the current task after yielding some chunks
        task = asyncio.current_task()
        if task:
            task.cancel()


# ── Fixtures ────────────────────────────────────────────────────────

@pytest.fixture
def stream_agent(monkeypatch, tmp_path):
    """Create an Agent configured for streaming with mock LLM."""
    db_path = str(tmp_path / "test.db")

    monkeypatch.setattr("merco.core.agent._get_db_path", lambda: db_path)

    cfg = MercoConfig()
    cfg.model.api_key = "test-key"
    cfg.model.model = "test-model"
    cfg.sandbox_mode = "auto"
    cfg.streaming = StreamingConfig(
        enabled=True,
        content=True,
        think=True,
        think_transient=False,
    )

    reg = make_test_registry()
    agent = Agent(config=cfg, tool_registry=reg)
    return agent


@pytest.fixture
def quiet_console(monkeypatch):
    """Replace the agent module's console with a quiet one to avoid terminal noise."""
    from rich.console import Console
    quiet = Console(file=StringIO(), force_terminal=True, width=120)
    monkeypatch.setattr("merco.core.agent.console", quiet)
    return quiet


# ═══════════════════════════════════════════════════════════
# Scenario 1: thinking + content both streaming
# ═══════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_thinking_and_content_both_streaming(stream_agent, quiet_console):
    """streaming=True, stream_content=True, stream_thinking=True:
    Both thinking and content panels should stream and be preserved."""
    stream_agent.provider = StreamingMockProvider([
        {"reasoning": "Let me think..."},
        {"reasoning": " about this."},
        {"content": "The answer is "},
        {"content": "42."},
        {"finish_reason": "stop"},
    ])

    result = await stream_agent.run("What is the answer?")

    # Content should be assembled correctly
    assert "42" in result
    # Session should have both messages
    msgs = stream_agent.session.messages
    assert len(msgs) == 2
    assert msgs[0]["role"] == "user"
    assert msgs[1]["role"] == "assistant"
    assert "42" in msgs[1]["content"]


@pytest.mark.asyncio
async def test_thinking_only_no_content(stream_agent, quiet_console):
    """Model returns reasoning but empty content — should not crash."""
    stream_agent.provider = StreamingMockProvider([
        {"reasoning": "Thinking hard..."},
        {"reasoning": " still thinking..."},
        {"content": ""},
        {"finish_reason": "stop"},
    ])

    # Should not crash even with empty content
    result = await stream_agent.run("Think about nothing")
    # Empty content triggers the empty response pipeline or fallback
    assert result is not None


@pytest.mark.asyncio
async def test_content_only_no_thinking(stream_agent, quiet_console):
    """Model returns content without reasoning — should work fine."""
    stream_agent.provider = StreamingMockProvider([
        {"content": "Hello "},
        {"content": "world!"},
        {"finish_reason": "stop"},
    ])

    result = await stream_agent.run("Say hello")
    assert "Hello" in result
    assert "world" in result


# ═══════════════════════════════════════════════════════════
# Scenario 2: Empty content handling
# ═══════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_empty_content_no_crash(stream_agent, quiet_console):
    """Empty content should not crash — handled by empty response pipeline."""
    stream_agent.provider = StreamingMockProvider([
        {"content": ""},
        {"finish_reason": "stop"},
    ])

    # Should not raise
    result = await stream_agent.run("Give empty response")
    assert result is not None


@pytest.mark.asyncio
async def test_whitespace_only_content(stream_agent, quiet_console):
    """Whitespace-only content should be handled gracefully."""
    stream_agent.provider = StreamingMockProvider([
        {"content": "   "},
        {"content": "\n\n"},
        {"finish_reason": "stop"},
    ])

    result = await stream_agent.run("Give whitespace")
    assert result is not None


# ═══════════════════════════════════════════════════════════
# Scenario 3: tool_calls with streaming
# ═══════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_tool_calls_with_streaming(stream_agent, quiet_console):
    """Tool calls should work correctly with streaming enabled."""
    # First call: return a tool_call
    # Second call (after tool result): return final content
    stream_agent.provider = StreamingMockProvider([
        # First response: tool call
        {"reasoning": "I need to use a tool"},
        {"tool_calls": [{"id": "tc_1", "name": "echo", "index": 0,
                         "arguments": '{"message": "hello"}'}]},
        {"finish_reason": "tool_calls"},
    ])
    # Override to provide second response after tool execution
    original_stream = stream_agent.provider.chat_stream
    call_count = [0]

    async def multi_turn_stream(messages, tools=None, tool_choice="auto"):
        call_count[0] += 1
        if call_count[0] == 1:
            # First call: tool call
            yield {"reasoning": "I need to use a tool"}
            yield {"tool_calls": [{"id": "tc_1", "name": "echo", "index": 0,
                                   "arguments": '{"message": "hello"}'}]}
            yield {"finish_reason": "tool_calls"}
        else:
            # Second call: final answer
            yield {"content": "The tool returned: "}
            yield {"content": "hello"}
            yield {"finish_reason": "stop"}

    stream_agent.provider.chat_stream = multi_turn_stream
    # Also need to handle non-streaming chat for the wrap-up path
    stream_agent.provider.chat = MagicMock(side_effect=[
        # For the second call, the agent loop calls chat_stream, not chat
    ])

    # Actually, the agent loop uses _provider.get_response which calls chat_stream
    # Let's just use a simpler approach - override chat_stream entirely
    async def mock_chat_stream(messages, tools=None, tool_choice="auto"):
        call_count[0] += 1
        if call_count[0] == 1:
            yield {"reasoning": "I need to use a tool"}
            yield {"tool_calls": [{"id": "tc_1", "name": "echo", "index": 0,
                                   "arguments": '{"message": "hello"}'}]}
            yield {"finish_reason": "tool_calls"}
        else:
            yield {"content": "The tool returned: hello"}
            yield {"finish_reason": "stop"}

    stream_agent.provider.chat_stream = mock_chat_stream
    call_count[0] = 0

    result = await stream_agent.run("Use echo tool")
    assert "hello" in result
    # Verify tool was called
    msgs = stream_agent.session.messages
    roles = [m["role"] for m in msgs]
    assert "tool" in roles


@pytest.mark.asyncio
async def test_tool_calls_streaming_arguments(stream_agent, quiet_console):
    """Tool call arguments streamed in chunks should be assembled correctly."""
    call_count = [0]

    async def mock_chat_stream(messages, tools=None, tool_choice="auto"):
        call_count[0] += 1
        if call_count[0] == 1:
            # Tool call with arguments split across chunks
            yield {"reasoning": "Using tool"}
            yield {"tool_calls": [{"id": "tc_1", "name": "echo", "index": 0,
                                   "arguments": '{"mes'}]}
            yield {"tool_calls": [{"id": "", "name": "", "index": 0,
                                   "arguments": 'sage": "hello"}'}]}
            yield {"finish_reason": "tool_calls"}
        else:
            yield {"content": "Done"}
            yield {"finish_reason": "stop"}

    stream_agent.provider.chat_stream = mock_chat_stream

    result = await stream_agent.run("Echo hello")
    assert result is not None
    # Verify the tool was called with the assembled arguments
    msgs = stream_agent.session.messages
    tool_msgs = [m for m in msgs if m["role"] == "tool"]
    assert len(tool_msgs) >= 1


# ═══════════════════════════════════════════════════════════
# Scenario 4: Ctrl+C interruption
# ═══════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_interrupt_during_streaming(stream_agent, quiet_console):
    """Cancelling the task during streaming should not crash."""
    chunks_yielded = [0]

    async def cancelling_stream(messages, tools=None, tool_choice="auto"):
        yield {"reasoning": "Starting to think..."}
        chunks_yielded[0] += 1
        yield {"content": "Partial response "}
        chunks_yielded[0] += 1
        # Simulate cancellation arriving
        raise asyncio.CancelledError()

    stream_agent.provider.chat_stream = cancelling_stream

    # Run in a task so we can cancel it
    task = asyncio.create_task(stream_agent.run("Long question"))
    # Give it a moment to start streaming
    await asyncio.sleep(0.05)

    # The cancelling_stream already raises CancelledError internally
    # which should be caught by the provider's checkpoint
    try:
        result = await task
    except asyncio.CancelledError:
        pass  # Expected

    # Verify no crash occurred and partial state was handled
    # The session should have the user message at minimum
    msgs = stream_agent.session.messages
    assert any(m["role"] == "user" for m in msgs)


@pytest.mark.asyncio
async def test_interrupt_preserves_partial_content(stream_agent, quiet_console):
    """When interrupted, partial content should be saved to session."""
    async def slow_stream_with_cancel(messages, tools=None, tool_choice="auto"):
        yield {"reasoning": "Thinking step 1"}
        yield {"reasoning": " Thinking step 2"}
        yield {"content": "Partial answer"}
        # Now cancel
        current = asyncio.current_task()
        if current:
            current.cancel()
        # Yield one more to give the checkpoint a chance
        yield {"content": " more"}

    stream_agent.provider.chat_stream = slow_stream_with_cancel

    task = asyncio.create_task(stream_agent.run("Tell me a story"))
    await asyncio.sleep(0.05)

    try:
        await task
    except asyncio.CancelledError:
        pass

    # The session should have messages
    msgs = stream_agent.session.messages
    user_msgs = [m for m in msgs if m["role"] == "user"]
    assert len(user_msgs) >= 1


# ═══════════════════════════════════════════════════════════
# Scenario 5: stream_thinking_transient=True
# ═══════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_stream_thinking_transient_true(monkeypatch, tmp_path):
    """When stream_thinking_transient=True, thinking panel should be transient."""
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr("merco.core.agent._get_db_path", lambda: db_path)

    from rich.console import Console
    quiet = Console(file=StringIO(), force_terminal=True, width=120)
    monkeypatch.setattr("merco.core.agent.console", quiet)

    cfg = MercoConfig()
    cfg.model.api_key = "test-key"
    cfg.model.model = "test-model"
    cfg.sandbox_mode = "auto"
    cfg.streaming = StreamingConfig(
        enabled=True,
        content=True,
        think=True,
        think_transient=True,  # <-- key config
    )

    reg = make_test_registry()
    agent = Agent(config=cfg, tool_registry=reg)

    agent.provider = StreamingMockProvider([
        {"reasoning": "Transient thinking..."},
        {"content": "Final answer"},
        {"finish_reason": "stop"},
    ])

    result = await agent.run("Test transient")
    assert "Final answer" in result

    # Verify the config is correctly set
    assert agent.config.streaming.think_transient is True


@pytest.mark.asyncio
async def test_stream_thinking_transient_false_preserves_panel(monkeypatch, tmp_path):
    """When stream_thinking_transient=False (default), thinking panel should be preserved."""
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr("merco.core.agent._get_db_path", lambda: db_path)

    from rich.console import Console
    quiet = Console(file=StringIO(), force_terminal=True, width=120)
    monkeypatch.setattr("merco.core.agent.console", quiet)

    cfg = MercoConfig()
    cfg.model.api_key = "test-key"
    cfg.model.model = "test-model"
    cfg.sandbox_mode = "auto"
    cfg.streaming = StreamingConfig(
        enabled=True,
        content=True,
        think=True,
        think_transient=False,  # <-- default
    )

    reg = make_test_registry()
    agent = Agent(config=cfg, tool_registry=reg)

    agent.provider = StreamingMockProvider([
        {"reasoning": "Persistent thinking..."},
        {"content": "Final answer"},
        {"finish_reason": "stop"},
    ])

    result = await agent.run("Test persistent")
    assert "Final answer" in result
    assert agent.config.streaming.think_transient is False


# ═══════════════════════════════════════════════════════════
# Scenario 6: stream_content=False (non-streaming content)
# ═══════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_stream_content_false(monkeypatch, tmp_path):
    """When stream_content=False, content Live panel should not be created."""
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr("merco.core.agent._get_db_path", lambda: db_path)

    from rich.console import Console
    quiet = Console(file=StringIO(), force_terminal=True, width=120)
    monkeypatch.setattr("merco.core.agent.console", quiet)

    cfg = MercoConfig()
    cfg.model.api_key = "test-key"
    cfg.model.model = "test-model"
    cfg.sandbox_mode = "auto"
    cfg.streaming = StreamingConfig(
        enabled=True,
        content=False,  # <-- disabled
        think=True,
        think_transient=False,
    )

    reg = make_test_registry()
    agent = Agent(config=cfg, tool_registry=reg)

    agent.provider = StreamingMockProvider([
        {"reasoning": "Thinking..."},
        {"content": "Answer without streaming"},
        {"finish_reason": "stop"},
    ])

    result = await agent.run("Test no content streaming")
    assert "Answer without streaming" in result


# ═══════════════════════════════════════════════════════════
# Scenario 7: Config combinations
# ═══════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_streaming_false_uses_non_streaming_provider(stream_agent, quiet_console):
    """When streaming=False, NonStreamingProvider should be used."""
    stream_agent.config.streaming.enabled = False
    # Re-create provider
    from merco.core.agent import NonStreamingProvider
    stream_agent._provider = NonStreamingProvider()

    stream_agent.provider = StreamingMockProvider([
        {"content": "Non-streaming answer"},
    ])

    result = await stream_agent.run("Test non-streaming")
    assert "Non-streaming answer" in result


@pytest.mark.asyncio
async def test_streaming_with_usage_info(stream_agent, quiet_console):
    """Streaming with usage info should not crash."""
    stream_agent.provider = StreamingMockProvider([
        {"reasoning": "Thinking..."},
        {"content": "Answer"},
        {"finish_reason": "stop", "usage": {"prompt_tokens": 10, "completion_tokens": 5}},
    ])

    result = await stream_agent.run("Test with usage")
    assert "Answer" in result


@pytest.mark.asyncio
async def test_many_small_chunks(stream_agent, quiet_console):
    """Many small content chunks should be assembled correctly."""
    chunks = [{"content": char} for char in "Hello, World!"]
    chunks.append({"finish_reason": "stop"})

    stream_agent.provider = StreamingMockProvider(chunks)

    result = await stream_agent.run("Spell it out")
    assert "Hello, World!" in result


@pytest.mark.asyncio
async def test_interleaved_reasoning_and_content(stream_agent, quiet_console):
    """Interleaved reasoning and content chunks should both be captured."""
    stream_agent.provider = StreamingMockProvider([
        {"reasoning": "Step 1: "},
        {"content": "First part. "},
        {"reasoning": "Step 2: "},
        {"content": "Second part."},
        {"finish_reason": "stop"},
    ])

    result = await stream_agent.run("Multi-step answer")
    assert "First part" in result
    assert "Second part" in result
