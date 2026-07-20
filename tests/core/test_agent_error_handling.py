"""Tests for Agent streaming error handling: error flag, panel display, re-raise."""
import asyncio
import pytest
from io import StringIO
from unittest.mock import MagicMock, patch
from rich.console import Console

from merco.core.agent import Agent, StreamingProvider
from merco.core.config import MercoConfig
from merco.memory.session_store import SessionStore
from merco.tools.registry import ToolRegistry


class _FailingStreamLLM:
    """Mock LLM whose chat_stream raises immediately."""
    model = "test-model"

    def __init__(self, exc: Exception):
        self._exc = exc
        self.calls = []

    async def chat_stream(self, messages, tools=None, tool_choice="auto"):
        self.calls.append({"messages": messages, "tools": tools})
        raise self._exc
        yield  # pragma: no cover

    async def chat(self, messages, tools=None, tool_choice="auto"):
        raise self._exc


async def _make_agent_with_failing_llm(monkeypatch, tmp_path, exc: Exception,
                                  streaming: bool = True) -> Agent:
    """Build Agent with _FailingStreamLLM injected directly (bypass plugin activation)."""
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr("merco.core.agent._get_db_path", lambda: db_path)

    cfg = MercoConfig()
    cfg.model.api_key = "test-key"
    cfg.model.model = "test-model"
    cfg.sandbox_mode = "auto"
    cfg.streaming = streaming
    cfg.stream_thinking = True
    cfg.stream_content = True
    cfg.stream_thinking_transient = False  # default: persistent panels
    cfg.memory_path = str(tmp_path / "memory")
    cfg.max_input_tokens = 8000
    cfg.compression_threshold = 0.8
    cfg.max_tool_calls = 20

    async def _fake_create(config, tool_registry=None):
        agent = Agent(config, tool_registry=tool_registry)
        agent._plugin_ctx = MagicMock()
        agent._session_store = SessionStore(db_path)
        agent.session = type(agent.session).resume_or_create(agent._session_store)
        agent._restore_context()
        agent.llm = _FailingStreamLLM(exc)  # inject failing LLM
        return agent

    monkeypatch.setattr(Agent, "create", staticmethod(_fake_create))
    reg = ToolRegistry()
    agent = await Agent.create(cfg, tool_registry=reg)
    return agent


class TestErrorFlag:
    def test_flag_exists_and_initialized_false(self, test_agent):
        """Agent should have _error_displayed_in_stream attr, False after init."""
        assert hasattr(test_agent, '_error_displayed_in_stream')
        assert test_agent._error_displayed_in_stream is False

    def test_flag_reset_on_run_entry(self, test_agent):
        """run() should reset the flag to False at entry."""
        test_agent._error_displayed_in_stream = True
        # Call just the first line of run() to verify reset; inspect the method.
        import inspect
        source = inspect.getsource(test_agent.run)
        assert "_error_displayed_in_stream = False" in source


class TestStreamingProviderError:
    @pytest.mark.asyncio
    async def test_reraises_error(self, tmp_path, monkeypatch):
        """StreamingProvider must re-raise errors so agent loop handles retry."""
        exc = Exception("502 bad gateway")
        exc.status_code = 502
        agent = await _make_agent_with_failing_llm(monkeypatch, tmp_path, exc)
        provider = StreamingProvider()
        fake_out = StringIO()
        import merco.core.agent as agent_mod
        con = Console(file=fake_out, force_terminal=True, width=120, color_system=None)
        with patch.object(agent_mod, "console", con):
            with pytest.raises(Exception, match="502 bad gateway"):
                await provider.get_response(
                    agent,
                    [{"role": "user", "content": "hi"}],
                    [])

    @pytest.mark.asyncio
    async def test_sets_error_flag_on_error(self, tmp_path, monkeypatch):
        exc = Exception("401 unauthorized")
        exc.status_code = 401
        agent = await _make_agent_with_failing_llm(monkeypatch, tmp_path, exc)
        provider = StreamingProvider()
        fake_out = StringIO()
        import merco.core.agent as agent_mod
        con = Console(file=fake_out, force_terminal=True, width=120, color_system=None)
        with patch.object(agent_mod, "console", con):
            with pytest.raises(Exception):
                await provider.get_response(
                    agent,
                    [{"role": "user", "content": "hi"}],
                    [])
        assert agent._error_displayed_in_stream is True

    @pytest.mark.asyncio
    async def test_error_panel_contains_error_info(self, tmp_path, monkeypatch):
        """When error occurs with empty bufs (default non-transient), error
        output is printed and contains error category."""
        exc = Exception("rate limit exceeded")
        exc.status_code = 429
        agent = await _make_agent_with_failing_llm(monkeypatch, tmp_path, exc)
        provider = StreamingProvider()
        fake_out = StringIO()
        import merco.core.agent as agent_mod
        con = Console(file=fake_out, force_terminal=True, width=120, color_system=None)
        with patch.object(agent_mod, "console", con):
            with pytest.raises(Exception):
                await provider.get_response(
                    agent,
                    [{"role": "user", "content": "hi"}],
                    [])
        output = fake_out.getvalue()
        # Non-transient + empty bufs triggers static print path
        assert "API" in output or "限流" in output or "429" in output

    @pytest.mark.asyncio
    async def test_cancelled_error_propagates_without_setting_error_flag(self, tmp_path, monkeypatch):
        """asyncio.CancelledError should re-raise without setting error flag."""
        class _CancelImmediateLLM:
            model = "test-model"
            calls = []
            async def chat_stream(self, messages, tools=None, tool_choice="auto"):
                raise asyncio.CancelledError()
                yield  # pragma: no cover

        db_path = str(tmp_path / "test.db")
        monkeypatch.setattr("merco.core.agent._get_db_path", lambda: db_path)
        cfg = MercoConfig()
        cfg.model.api_key = "test"
        cfg.model.model = "m"
        cfg.sandbox_mode = "auto"
        cfg.streaming = True
        cfg.stream_thinking = True
        cfg.stream_content = True
        cfg.stream_thinking_transient = False
        cfg.memory_path = str(tmp_path / "mem")
        cfg.max_input_tokens = 8000
        cfg.compression_threshold = 0.8
        cfg.max_tool_calls = 20

        async def _fake_create(config, tool_registry=None):
            a = Agent(config, tool_registry=tool_registry)
            a._plugin_ctx = MagicMock()
            a._session_store = SessionStore(db_path)
            a.session = type(a.session).resume_or_create(a._session_store)
            a._restore_context()
            a.llm = _CancelImmediateLLM()
            return a

        monkeypatch.setattr(Agent, "create", staticmethod(_fake_create))
        agent = await Agent.create(cfg, tool_registry=ToolRegistry())
        provider = StreamingProvider()
        fake_out = StringIO()
        import merco.core.agent as agent_mod
        con = Console(file=fake_out, force_terminal=True, width=120, color_system=None)
        with patch.object(agent_mod, "console", con):
            with pytest.raises(asyncio.CancelledError):
                await provider.get_response(
                    agent,
                    [{"role": "user", "content": "hi"}],
                    [])
        # CancelledError path must NOT set error-displayed flag
        assert agent._error_displayed_in_stream is False


class TestReset:
    def test_reset_resets_error_flag(self, test_agent):
        test_agent._error_displayed_in_stream = True
        test_agent.reset()
        assert test_agent._error_displayed_in_stream is False


class TestStreamLoggerNoTracebackLeak:
    """merco.core.agent 的 StreamingProvider 错误日志不应包含 exc_info=True。

    原因：非 debug 阶段 logger.warning + exc_info=True 会把整段 Python traceback
    写到 stderr，被 TUI 终端直接接管显示 — 用户看到一坨 stacktrace。
    契约：exc_info=False；traceback 改走 logger.debug(..., exc_info=True)，仅在
    显式启用 DEBUG 日志时才见。
    """

    def test_streaming_provider_error_logger_does_not_include_exc_info(self, caplog):
        """源码静态检查：merco/core/agent.py StreamingProvider 的 logger.warning 调用
        不应含 exc_info=True。logger.debug 含 exc_info=True 是允许的（仅 debug 阶段输出）。
        """
        import inspect
        from merco.core.agent import StreamingProvider
        source = inspect.getsource(StreamingProvider.get_response)
        assert "StreamingProvider API 错误" in source
        for line in source.splitlines():
            stripped = line.strip()
            if "StreamingProvider API 错误" in stripped and "logger.warning" in stripped:
                assert "exc_info=True" not in stripped, (
                    f"StreamingProvider logger.warning 不应含 exc_info=True：\n  {stripped}"
                )
