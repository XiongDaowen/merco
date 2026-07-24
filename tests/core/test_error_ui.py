"""Unit tests for merco.core.llm.error_ui."""
import pytest

from merco.core.llm.error_ui import (
    ErrorInfo,
    classify_error,
    sanitize_message,
)


class _FakeExc(Exception):
    def __init__(self, msg="boom", status_code=None):
        super().__init__(msg)
        self.status_code = status_code


class TestClassifyError:
    def test_401_is_auth_failure(self):
        info = classify_error(_FakeExc("Unauthorized", status_code=401))
        assert "认证" in info.label
        assert info.hint  # non-empty hint

    def test_403_is_permission_denied(self):
        info = classify_error(_FakeExc("Forbidden", status_code=403))
        assert "权限" in info.label

    def test_404_is_not_found(self):
        info = classify_error(_FakeExc("model not found", status_code=404))
        assert "不存在" in info.label

    def test_413_is_too_long(self):
        info = classify_error(_FakeExc("context length exceeded", status_code=413))
        assert "长" in info.label

    def test_429_is_rate_limit(self):
        info = classify_error(_FakeExc("rate limit", status_code=429))
        assert "限流" in info.label

    def test_5xx_is_server_error(self):
        info = classify_error(_FakeExc("bad gateway", status_code=502))
        assert "502" in info.label
        assert "服务端" in info.label

    def test_500_range_covered(self):
        for code in (500, 502, 503, 504):
            info = classify_error(_FakeExc("err", status_code=code))
            assert str(code) in info.label

    def test_timeout_exception(self):
        class TimeoutExc(Exception):
            pass
        info = classify_error(TimeoutExc("read timeout"))
        assert "超时" in info.label

    def test_connection_exception(self):
        class ConnExc(Exception):
            pass
        info = classify_error(ConnExc("connection refused"))
        assert "连接" in info.label

    def test_plain_exception_falls_back_to_class_name(self):
        info = classify_error(Exception("something weird"))
        assert info.label  # non-empty
        assert info.hint

    def test_preserves_original_exception(self):
        exc = _FakeExc("x", status_code=500)
        info = classify_error(exc)
        assert info.exc is exc


class TestSanitizeMessage:
    def test_redacts_api_key(self):
        exc = Exception("bad api_key=sk-12345abcdef")
        msg = sanitize_message(exc)
        assert "sk-12345" not in msg
        assert "脱敏" in msg

    def test_redacts_authorization_header(self):
        exc = Exception("header: Authorization Bearer xxxx")
        msg = sanitize_message(exc)
        assert "脱敏" in msg

    def test_truncates_long_messages(self):
        exc = Exception("x" * 1000)
        msg = sanitize_message(exc, max_len=100)
        assert len(msg) <= 100 + 1  # +1 for ellipsis "…"

    def test_short_message_passthrough(self):
        exc = Exception("simple error")
        msg = sanitize_message(exc)
        assert msg == "simple error"

    def test_does_not_redact_word_tokens(self):
        exc = Exception("This model's maximum context length is 8192 tokens")
        msg = sanitize_message(exc)
        assert "tokens" in msg
        assert "脱敏" not in msg


from rich.panel import Panel


class _DummyExc(Exception):
    def __init__(self, msg="boom", status_code=None):
        super().__init__(msg)
        self.status_code = status_code


class TestBuildErrorPanel:
    def test_returns_panel(self):
        from merco.core.llm.error_ui import build_error_panel
        info = ErrorInfo("连接错误", "检查网络", _DummyExc("fail"))
        panel = build_error_panel(info)
        assert isinstance(panel, Panel)
        assert panel.border_style == "red"
        assert "API 错误" in str(panel.title)

    def test_panel_contains_label(self):
        from merco.core.llm.error_ui import build_error_panel
        info = ErrorInfo("认证失败", "检查 key", _DummyExc("bad key"))
        panel = build_error_panel(info)
        renderable = panel.renderable
        text = str(renderable)
        assert "认证失败" in text

    def test_panel_contains_sanitized_detail(self):
        from merco.core.llm.error_ui import build_error_panel
        exc = _DummyExc("connection reset by peer")
        info = ErrorInfo("连接错误", "检查网络", exc)
        panel = build_error_panel(info)
        assert "connection reset" in str(panel.renderable)

    def test_panel_title(self):
        from merco.core.llm.error_ui import build_error_panel
        info = ErrorInfo("请求限流", "", _DummyExc("rate limit", status_code=429))
        panel = build_error_panel(info)
        assert panel.title_align == "left"
        assert panel.padding == (0, 1)


class TestBuildRetryLine:
    def test_format_with_wait_and_compress(self):
        from merco.core.llm.error_ui import build_retry_line
        info = ErrorInfo("请求限流", "", _DummyExc(status_code=429))
        line = build_retry_line(info, 1, 3, ["等待 3.0s", "压缩上下文"])
        assert "↻" in line
        assert "第 1/3 次" in line
        assert "请求限流" in line
        assert "等待 3.0s" in line
        assert "压缩上下文" in line
        assert line.startswith("[yellow]")
        assert line.endswith("[/yellow]")

    def test_format_immediate_retry_when_no_actions(self):
        from merco.core.llm.error_ui import build_retry_line
        info = ErrorInfo("服务端错误 (500)", "", _DummyExc(status_code=500))
        line = build_retry_line(info, 2, 3, [])
        assert "第 2/3 次" in line
        assert "立即重试" in line

    def test_format_single_action(self):
        from merco.core.llm.error_ui import build_retry_line
        info = ErrorInfo("服务端错误 (500)", "", _DummyExc(status_code=500))
        line = build_retry_line(info, 2, 3, ["立即重试"])
        assert "立即重试" in line
        assert " + " not in line


class TestErrorMessage:
    def test_starts_with_x_marker(self):
        from merco.core.llm.error_ui import error_message
        info = ErrorInfo("请求限流", "稍后重试", _DummyExc("rate limit"))
        msg = error_message(info)
        assert msg.startswith("❌ ")

    def test_contains_label_hint_detail(self):
        from merco.core.llm.error_ui import error_message
        exc = _DummyExc("gateway timeout", status_code=504)
        info = ErrorInfo("服务端错误 (504)", "稍后重试", exc)
        msg = error_message(info)
        assert "服务端错误 (504)" in msg
        assert "稍后重试" in msg
        assert "gateway timeout" in msg

    def test_redacts_sensitive_in_final_message(self):
        from merco.core.llm.error_ui import error_message
        exc = _DummyExc("bad api_key=sk-secret1234")
        info = ErrorInfo("认证失败", "check key", exc)
        msg = error_message(info)
        assert "sk-secret1234" not in msg
        assert "脱敏" in msg


class TestRetrySpinner:
    @pytest.mark.asyncio
    async def test_short_wait_is_no_op(self):
        """For seconds <= 1, spinner should yield immediately without creating Live."""
        from io import StringIO

        from rich.console import Console

        from merco.core.llm.error_ui import retry_spinner
        con = Console(file=StringIO(), force_terminal=True, width=120)
        entered = False
        async with retry_spinner("x", 0.5, con):
            entered = True
        assert entered is True
        # Short wait: no spinner output expected (transient Live clears itself
        # and no update would happen within <1s). We just verify no exception.

    @pytest.mark.asyncio
    async def test_spinner_updates_during_wait(self):
        """For seconds > 1, spinner should be a working async ctx manager."""
        import asyncio
        from io import StringIO

        from rich.console import Console

        from merco.core.llm.error_ui import retry_spinner
        con = Console(file=StringIO(), force_terminal=True, width=120)
        async with retry_spinner("请求限流", 1.2, con):
            await asyncio.sleep(0.3)
        # Should complete without exception and without leaving output
        # (transient Live clears on exit)
