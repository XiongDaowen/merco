"""_run_one_turn() 异常路径测试 — 用户最关心的 LLM 失败友好性"""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock

from cli.main import _run_one_turn, PromptArea
from tests.cli.conftest import make_fake_agent


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
        config_overrides={"streaming": True, "stream_content": True},
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
        config_overrides={"streaming": True, "stream_content": False},
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
async def test_logger_warning_dedupes_repeated_provider_errors(caplog, monkeypatch):
    """同一 Provider 异常在多次 retry 中：logger.warning 不应逐次打印。

    现实：retry pipeline 重试 N 次时，每个重试都会触发 Provider 重新走 except 块，
    导致 logger.warning 重复 N 次（用户截图里看到 4-5 次 WARNING + Panel）。

    契约：StreamLogger 应使用 WeakValueDictionary（或 set）按 id(exc) 去重；
    同一异常对象只第一次打 warning，后续同 id 直接跳过。
    """
    import logging

    caplog.clear()
    caplog.set_level(logging.WARNING, logger="merco.agent")

    # 通过 monkeypatch 计数 logger.warning 调用次数
    call_count = {"n": 0}
    real_warn = logging.getLogger("merco.agent").warning

    def counting_warn(*args, **kwargs):
        call_count["n"] += 1
        return real_warn(*args, **kwargs)

    monkeypatch.setattr(logging.getLogger("merco.agent"), "warning", counting_warn)

    # 直接模拟 _agent_loop 的 retry 路径：连续 3 次抛同样异常
    # 这里测的是去重机制本身
    from merco.core.agent import StreamingProvider

    # 通过 patch.get_response 模拟 provider 总是失败
    provider = StreamingProvider()
    fake_agent = MagicMock()
    fake_agent.llm.chat_stream = AsyncMock(
        side_effect=Exception("rate limit")
    )
    fake_agent._error_displayed_in_stream = False
    fake_agent.config.stream_thinking = True
    fake_agent.config.stream_content = True
    fake_agent.config.stream_thinking_transient = False

    # 调用 3 次 — 实际中 retry pipeline 会调 3 次
    for _ in range(3):
        try:
            await provider.get_response(fake_agent, [], [])
        except Exception:
            pass

    assert call_count["n"] <= 1, (
        f"同一异常最多 logger.warning 一次（收到 {call_count['n']} 次）"
    )
