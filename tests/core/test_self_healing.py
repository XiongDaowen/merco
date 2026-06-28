"""self_healing 错误分类测试"""
import pytest
from merco.core.self_healing import _is_retryable_llm_error


class FakeAPIStatusError(Exception):
    """模拟 openai.APIStatusError，仅带 _is_retryable_llm_error 用到的属性"""
    def __init__(self, status_code: int = 0, message: str = ""):
        self.status_code = status_code
        self._message = message

    def __str__(self):
        return self._message


# 注入到 openai 模块，让 _is_retryable_llm_error 的 isinstance 检查通过
@pytest.fixture(autouse=True)
def _patch_api_status_error(monkeypatch):
    import openai
    monkeypatch.setattr(openai, "APIStatusError", FakeAPIStatusError, raising=False)


def test_retryable_on_429():
    assert _is_retryable_llm_error(FakeAPIStatusError(429)) is True


def test_retryable_on_5xx():
    for code in (500, 502, 503, 504):
        assert _is_retryable_llm_error(FakeAPIStatusError(code)) is True


def test_retryable_on_413():
    assert _is_retryable_llm_error(FakeAPIStatusError(413)) is True


def test_not_retryable_on_400():
    assert _is_retryable_llm_error(FakeAPIStatusError(400)) is False


def test_not_retryable_on_401():
    assert _is_retryable_llm_error(FakeAPIStatusError(401)) is False


def test_not_retryable_on_normal_exception():
    assert _is_retryable_llm_error(ValueError("oops")) is False


def test_retryable_on_rate_limit_keyword():
    assert _is_retryable_llm_error(FakeAPIStatusError(400, "rate limit exceeded")) is True


def test_retryable_on_context_too_long_keyword():
    for msg in ("context length too long", "too long for this model",
                "maximum context exceeded", "reduce the length",
                "prompt too long, please shorten"):
        assert _is_retryable_llm_error(FakeAPIStatusError(400, msg)) is True


def test_retryable_on_overloaded_keyword():
    assert _is_retryable_llm_error(FakeAPIStatusError(503, "server overloaded")) is True


def test_retryable_on_temporarily_unavailable_keyword():
    assert _is_retryable_llm_error(FakeAPIStatusError(502, "temporarily unavailable")) is True


def test_not_retryable_on_irrelevant_400():
    assert _is_retryable_llm_error(FakeAPIStatusError(400, "invalid model name")) is False


def test_llm_errors_module_imports():
    from merco.core.llm.errors import llm_error, _is_retryable_llm_error
    assert llm_error.__name__ == "llm_error"
    assert _is_retryable_llm_error.__name__ == "_is_retryable_llm_error"
