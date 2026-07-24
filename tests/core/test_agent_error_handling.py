"""Tests for Agent streaming error handling: error flag, panel display, re-raise."""

import asyncio
from io import StringIO
from unittest.mock import MagicMock, patch

import pytest
from rich.console import Console

from merco.core.agent import Agent, StreamingProvider
from merco.core.config import MercoConfig, StreamingConfig
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


async def _make_agent_with_failing_llm(monkeypatch, tmp_path, exc: Exception, streaming: bool = True) -> Agent:
    """Build Agent with _FailingStreamLLM injected directly (bypass plugin activation)."""
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr("merco.core.agent._get_db_path", lambda: db_path)

    cfg = MercoConfig()
    cfg.model.api_key = "test-key"
    cfg.model.model = "test-model"
    cfg.sandbox_mode = "auto"
    cfg.streaming = StreamingConfig(
        enabled=streaming,
        think=True,
        content=True,
        think_transient=False,
    )
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
        agent.provider = _FailingStreamLLM(exc)  # inject failing provider
        return agent

    monkeypatch.setattr(Agent, "create", staticmethod(_fake_create))
    reg = ToolRegistry()
    agent = await Agent.create(cfg, tool_registry=reg)
    return agent


class TestErrorFlag:
    def test_flag_exists_and_initialized_false(self, test_agent):
        """Agent should have _error_displayed_in_stream attr, False after init."""
        assert hasattr(test_agent, "_error_displayed_in_stream")
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
                await provider.get_response(agent, [{"role": "user", "content": "hi"}], [])

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
                await provider.get_response(agent, [{"role": "user", "content": "hi"}], [])
        assert agent._error_displayed_in_stream is True

    @pytest.mark.asyncio
    async def test_error_panel_contains_error_info(self, tmp_path, monkeypatch):
        """Provider 抛异常时：_error_displayed_in_stream=True，异常 re-raise。

        重构后 Provider 不再 console.print 完整 ⚠ Panel（避免 retry 时 Panel 叠层）。
        动态提示由 Live 内嵌的一行 red 文案负责；完整 Panel 由 _agent_loop 返回
        llm_error(e) 字符串后在 _run_one_turn 渲染。
        """
        exc = Exception("rate limit exceeded")
        exc.status_code = 429
        agent = await _make_agent_with_failing_llm(monkeypatch, tmp_path, exc)
        provider = StreamingProvider()
        fake_out = StringIO()
        import merco.core.agent as agent_mod

        con = Console(file=fake_out, force_terminal=True, width=120, color_system=None)
        with patch.object(agent_mod, "console", con):
            with pytest.raises(Exception):
                await provider.get_response(agent, [{"role": "user", "content": "hi"}], [])
        assert agent._error_displayed_in_stream is True

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
        cfg.streaming = StreamingConfig(
            enabled=True,
            think=True,
            content=True,
            think_transient=False,
        )
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
            a.provider = _CancelImmediateLLM()
            return a

        monkeypatch.setattr(Agent, "create", staticmethod(_fake_create))
        agent = await Agent.create(cfg, tool_registry=ToolRegistry())
        provider = StreamingProvider()
        fake_out = StringIO()
        import merco.core.agent as agent_mod

        con = Console(file=fake_out, force_terminal=True, width=120, color_system=None)
        with patch.object(agent_mod, "console", con):
            with pytest.raises(asyncio.CancelledError):
                await provider.get_response(agent, [{"role": "user", "content": "hi"}], [])
        # CancelledError path must NOT set error-displayed flag
        assert agent._error_displayed_in_stream is False


class TestReset:
    def test_reset_resets_error_flag(self, test_agent):
        test_agent._error_displayed_in_stream = True
        test_agent.reset()
        assert test_agent._error_displayed_in_stream is False


class TestStreamLoggerNoTracebackLeak:
    """merco.core.agent 的 StreamingProvider 错误日志行为契约。

    - 非 debug 模式：logger.info 输出被 WARNING 阈值抑制，stderr 无输出
    - debug 模式：logger.info + logger.debug(exc_info=True) 两者都可见
    - 无论何种模式：不应有 logger.warning(exc_info=True)
    """

    def test_streaming_provider_error_uses_info_not_warning_with_exc_info(self, caplog):
        """静态检查：merco/core/agent.py StreamingProvider 的错误日志中
        logger.warning 不应出现（已被 logger.info 替代）。
        """
        import inspect

        from merco.core.agent import StreamingProvider

        source = inspect.getsource(StreamingProvider.get_response)
        assert "StreamingProvider API 错误" in source
        for line in source.splitlines():
            stripped = line.strip()
            if "StreamingProvider API 错误" in stripped and "logger.warning" in stripped:
                raise AssertionError(f"StreamingProvider 不应使用 logger.warning：\n  {stripped}")
