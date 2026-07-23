"""_run_one_turn() 异常路径测试 — 用户最关心的 LLM 失败友好性"""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock

from cli.main import _run_one_turn, PromptArea
from tests.cli.conftest import make_fake_agent
from merco.core.config import StreamingConfig


class FakeDriver:
    """可配置返回值/异常的 driver 替身"""

    def __init__(self, inputs=None, raises=None):
        self._inputs = list(inputs or [])
        self._raises = raises
        self.get_input_calls = 0

    async def get_input(self, prompt):
        self.get_input_calls += 1
        if self._raises is not None:
            raise self._raises
        if not self._inputs:
            raise EOFError
        return self._inputs.pop(0)


# ─────────── 基线 / 正常路径 ───────────


@pytest.mark.asyncio
async def test_baseline_success_renders_panel_non_streaming(capture_console):
    """非流式：返回字符串 → Panel(Markdown(response)) 输出，含 'hi'"""
    capture, buf = capture_console
    agent = make_fake_agent(run_return="hi")
    driver = FakeDriver(inputs=["hello"])
    area = PromptArea()
    handle_cmd = AsyncMock(return_value=True)
    current_task_ref = [None]

    result = await _run_one_turn(
        agent, area, driver, handle_cmd, current_task_ref, console_obj=capture,
    )

    text = capture.export_text()
    assert "hi" in text
    assert result == "continue"


@pytest.mark.asyncio
async def test_stream_mode_suppresses_panel(capture_console):
    """流式 (streaming=True, stream_content=True) 下不打 Panel"""
    capture, buf = capture_console
    agent = make_fake_agent(
        run_return="this should NOT be wrapped",
        config_overrides={"streaming": StreamingConfig(enabled=True, content=True)},
    )
    driver = FakeDriver(inputs=["hi"])
    area = PromptArea()
    handle_cmd = AsyncMock(return_value=True)
    current_task_ref = [None]

    await _run_one_turn(
        agent, area, driver, handle_cmd, current_task_ref, console_obj=capture,
    )

    text = capture.export_text()
    assert "Agent" in text  # c.rule("[bold]Agent[/bold]") 渲染文本


@pytest.mark.asyncio
async def test_stream_mode_but_no_stream_content_still_panels(capture_console):
    """streaming=True 但 stream_content=False：仍打 Panel（回归保护）"""
    capture, buf = capture_console
    agent = make_fake_agent(
        run_return="response",
        config_overrides={"streaming": StreamingConfig(enabled=True, content=False)},
    )
    driver = FakeDriver(inputs=["hi"])
    area = PromptArea()
    handle_cmd = AsyncMock(return_value=True)
    current_task_ref = [None]

    await _run_one_turn(
        agent, area, driver, handle_cmd, current_task_ref, console_obj=capture,
    )

    text = capture.export_text()
    assert "response" in text


@pytest.mark.asyncio
async def test_empty_response_does_not_render_panel(capture_console):
    """agent.run() 返回空字符串：不打 Panel，无 crash"""
    capture, buf = capture_console
    agent = make_fake_agent(run_return="")
    driver = FakeDriver(inputs=["hi"])
    area = PromptArea()
    handle_cmd = AsyncMock(return_value=True)
    current_task_ref = [None]

    result = await _run_one_turn(
        agent, area, driver, handle_cmd, current_task_ref, console_obj=capture,
    )
    assert result == "continue"


# ─────────── 异常路径（核心）───────────


@pytest.mark.asyncio
async def test_runtime_error_shows_red_friendly_text_not_traceback(capture_console):
    """RuntimeError → 显示 [red]错误: <e>[/red]，**禁止** traceback 裸奔"""
    capture, buf = capture_console
    agent = make_fake_agent(
        run_side_effect=RuntimeError("rate limit exceeded")
    )
    driver = FakeDriver(inputs=["hi"])
    area = PromptArea()
    handle_cmd = AsyncMock(return_value=True)
    current_task_ref = [None]

    await _run_one_turn(
        agent, area, driver, handle_cmd, current_task_ref, console_obj=capture,
    )

    markup = capture.get_markup()
    text = capture.export_text()
    assert "[red]错误: rate limit exceeded[/red]" in markup
    assert "Traceback" not in text
    assert 'File "' not in text
    assert "RuntimeError" not in text


@pytest.mark.asyncio
async def test_connection_error_shows_friendly_text(capture_console):
    """ConnectionError → 显示 [red]错误: ...[/red]，无 traceback"""
    capture, buf = capture_console
    agent = make_fake_agent(
        run_side_effect=ConnectionError("network unreachable")
    )
    driver = FakeDriver(inputs=["hi"])
    area = PromptArea()
    handle_cmd = AsyncMock(return_value=True)
    current_task_ref = [None]

    await _run_one_turn(
        agent, area, driver, handle_cmd, current_task_ref, console_obj=capture,
    )

    markup = capture.get_markup()
    text = capture.export_text()
    assert "[red]错误: network unreachable[/red]" in markup
    assert "Traceback" not in text


@pytest.mark.asyncio
async def test_timeout_error_shows_friendly_text(capture_console):
    """asyncio.TimeoutError → 友好提示"""
    capture, buf = capture_console
    agent = make_fake_agent(
        run_side_effect=asyncio.TimeoutError("LLM timeout")
    )
    driver = FakeDriver(inputs=["hi"])
    area = PromptArea()
    handle_cmd = AsyncMock(return_value=True)
    current_task_ref = [None]

    await _run_one_turn(
        agent, area, driver, handle_cmd, current_task_ref, console_obj=capture,
    )

    markup = capture.get_markup()
    text = capture.export_text()
    assert "[red]错误: LLM timeout[/red]" in markup
    assert "Traceback" not in text


@pytest.mark.asyncio
async def test_cancelled_error_shows_dim_not_red(capture_console):
    """CancelledError → [dim]操作已取消[/dim]，**不是** [red]错误"""
    capture, buf = capture_console
    agent = make_fake_agent(
        run_side_effect=asyncio.CancelledError()
    )
    driver = FakeDriver(inputs=["hi"])
    area = PromptArea()
    handle_cmd = AsyncMock(return_value=True)
    current_task_ref = [None]

    await _run_one_turn(
        agent, area, driver, handle_cmd, current_task_ref, console_obj=capture,
    )

    markup = capture.get_markup()
    text = capture.export_text()
    assert "[dim]操作已取消[/dim]" in markup
    # 必须不含 — CancelledError 不应被当 error 处理
    assert "[red]错误:" not in markup
    assert "CancelledError" not in text


@pytest.mark.asyncio
async def test_eof_error_propagates_from_driver(capture_console):
    """driver 抛 EOFError → 向上传播（由 repl() 层捕获并打印 [dim]再见！[/dim]）"""
    capture, buf = capture_console
    agent = make_fake_agent()
    driver = FakeDriver(raises=EOFError())
    area = PromptArea()
    handle_cmd = AsyncMock(return_value=True)
    current_task_ref = [None]

    with pytest.raises(EOFError):
        await _run_one_turn(
            agent, area, driver, handle_cmd, current_task_ref, console_obj=capture,
        )


@pytest.mark.asyncio
async def test_keyboard_interrupt_propagates_from_driver(capture_console):
    """driver 抛 KeyboardInterrupt → 向上传播（由 repl() 层捕获并打印 [dim]再见！[/dim]）"""
    capture, buf = capture_console
    agent = make_fake_agent()
    driver = FakeDriver(raises=KeyboardInterrupt())
    area = PromptArea()
    handle_cmd = AsyncMock(return_value=True)
    current_task_ref = [None]

    with pytest.raises(KeyboardInterrupt):
        await _run_one_turn(
            agent, area, driver, handle_cmd, current_task_ref, console_obj=capture,
        )


@pytest.mark.asyncio
async def test_slash_command_returns_continue(capture_console):
    """输入 '/help' → handle_command(user_input, agent) 被调用，REPL 继续"""
    capture, buf = capture_console
    agent = make_fake_agent()
    driver = FakeDriver(inputs=["/help"])
    area = PromptArea()
    handle_cmd = AsyncMock(return_value=True)  # True = 继续
    current_task_ref = [None]

    result = await _run_one_turn(
        agent, area, driver, handle_cmd, current_task_ref, console_obj=capture,
    )
    assert result == "continue"
    handle_cmd.assert_called_once_with("/help", agent)


@pytest.mark.asyncio
async def test_slash_command_returns_exit_breaks_repl(capture_console):
    """handle_command 返回 False（/exit）→ REPL 退出"""
    capture, buf = capture_console
    agent = make_fake_agent()
    driver = FakeDriver(inputs=["/exit"])
    area = PromptArea()
    handle_cmd = AsyncMock(return_value=False)
    current_task_ref = [None]

    result = await _run_one_turn(
        agent, area, driver, handle_cmd, current_task_ref, console_obj=capture,
    )

    assert result == "exit"
    handle_cmd.assert_called_once_with("/exit", agent)


@pytest.mark.asyncio
async def test_empty_input_returns_continue(capture_console):
    """空输入 → 跳过本轮，返回 continue"""
    capture, buf = capture_console
    agent = make_fake_agent()
    driver = FakeDriver(inputs=["   "])  # 只有空白
    area = PromptArea()
    handle_cmd = AsyncMock()
    current_task_ref = [None]

    result = await _run_one_turn(
        agent, area, driver, handle_cmd, current_task_ref, console_obj=capture,
    )

    assert result == "continue"
    handle_cmd.assert_not_called()
    agent.run.assert_not_called()


# ─────────── Bug 修复契约（2026-07-20）───────────
# 失败时 UI 不应：
#   1. 把 Python traceback 泄漏到 capture output（non-debug 阶段）
#   2. 重复输出同一个错误（panel + simple red 错误行各一次）


@pytest.mark.asyncio
async def test_provider_error_uses_logger_info_not_warning(caplog, monkeypatch):
    """Provider 异常时使用 logger.info（非 debug 模式不可见），不用 logger.warning。

    注意：retry 时每次 chat_stream 抛新 Exception 对象，WeakSet 去重无效。
    真正的"不重复"保证来自：info 在 non-debug 模式被 WARNING 阈值抑制。
    """
    import logging

    caplog.clear()
    caplog.set_level(logging.DEBUG, logger="merco.agent")

    count = {"info": 0, "warning": 0}

    real_info = logging.getLogger("merco.agent").info
    real_warning = logging.getLogger("merco.agent").warning

    def counting_info(*a, **kw):
        count["info"] += 1
        return real_info(*a, **kw)

    def counting_warning(*a, **kw):
        count["warning"] += 1
        return real_warning(*a, **kw)

    monkeypatch.setattr(logging.getLogger("merco.agent"), "info", counting_info)
    monkeypatch.setattr(logging.getLogger("merco.agent"), "warning", counting_warning)

    from merco.core.agent import StreamingProvider

    provider = StreamingProvider()
    fake_agent = MagicMock()
    fake_agent.provider.chat_stream = AsyncMock(
        side_effect=Exception("rate limit")
    )
    fake_agent._error_displayed_in_stream = False
    fake_agent.config.streaming = StreamingConfig(think=True, content=True, think_transient=False)

    for _ in range(3):
        try:
            await provider.get_response(fake_agent, [], [])
        except Exception:
            pass

    assert count["warning"] == 0, "不应使用 logger.warning"
    assert count["info"] >= 1, "应使用 logger.info"
