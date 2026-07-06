"""Unit tests for merco.core.llm.error_ui."""
import pytest

from merco.core.llm.error_ui import (
    ErrorInfo, classify_error, sanitize_message,
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
