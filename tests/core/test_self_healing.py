"""self_healing / errors module tests (updated after _is_retryable_llm_error removal)."""
import pytest

from merco.core.pipeline import RecoveryContext


class _FakeExc(Exception):
    def __init__(self, msg="err", status_code=None):
        super().__init__(msg)
        self.status_code = status_code


# ── WaitRecovery covers the retryability logic formerly in _is_retryable_llm_error ──

@pytest.mark.asyncio
async def test_429_is_retryable_via_wait():
    from merco.core.recovery.wait import WaitRecovery
    rec = WaitRecovery()
    ctx = RecoveryContext(error=_FakeExc("rate limit", status_code=429))
    assert await rec.attempt(ctx) is True


@pytest.mark.asyncio
async def test_5xx_is_retryable_via_wait():
    from merco.core.recovery.wait import WaitRecovery
    rec = WaitRecovery()
    for code in (500, 502, 503, 504):
        ctx = RecoveryContext(error=_FakeExc("err", status_code=code))
        assert await rec.attempt(ctx) is True


@pytest.mark.asyncio
async def test_413_passes_to_compress_not_wait():
    from merco.core.recovery.wait import WaitRecovery
    rec = WaitRecovery()
    ctx = RecoveryContext(error=_FakeExc("too long", status_code=413))
    assert await rec.attempt(ctx) is False
    # compress handles it
    from merco.context.recovery import ContextCompressRecovery
    crec = ContextCompressRecovery()
    ctx2 = RecoveryContext(error=_FakeExc("too long", status_code=413), context_tokens=100)
    assert await crec.attempt(ctx2) is True


@pytest.mark.asyncio
async def test_normal_exception_gets_backoff():
    """Non-HTTP exceptions (network errors) get backoff now (no gating)."""
    from merco.core.recovery.wait import WaitRecovery
    rec = WaitRecovery()
    ctx = RecoveryContext(error=ValueError("oops"))
    assert await rec.attempt(ctx) is True  # unknown → shorter backoff


@pytest.mark.asyncio
async def test_rate_limit_keyword_detected():
    from merco.core.recovery.wait import WaitRecovery
    rec = WaitRecovery()
    ctx = RecoveryContext(error=_FakeExc("rate limit exceeded", status_code=400))
    assert await rec.attempt(ctx) is True


@pytest.mark.asyncio
async def test_context_too_long_keyword_passes_to_compress():
    from merco.core.recovery.wait import WaitRecovery
    rec = WaitRecovery()
    for msg in ("context length too long", "maximum context exceeded",
                "prompt too long, please shorten"):
        ctx = RecoveryContext(error=_FakeExc(msg, status_code=400))
        assert await rec.attempt(ctx) is False


@pytest.mark.asyncio
async def test_too_long_and_context_in_body_passes_to_compress():
    from merco.core.recovery.wait import WaitRecovery
    rec = WaitRecovery()
    ctx = RecoveryContext(error=_FakeExc("input too long for context window", status_code=400))
    assert await rec.attempt(ctx) is False


@pytest.mark.asyncio
async def test_temporarily_unavailable_gets_backoff():
    from merco.core.recovery.wait import WaitRecovery
    rec = WaitRecovery()
    ctx = RecoveryContext(error=_FakeExc("temporarily unavailable", status_code=503))
    assert await rec.attempt(ctx) is True


def test_errors_module_no_longer_exports_is_retryable():
    import merco.core.llm.errors as errors_mod
    assert not hasattr(errors_mod, "_is_retryable_llm_error")
    assert callable(errors_mod.llm_error)


def test_llm_errors_module_imports():
    from merco.core.llm.errors import llm_error
    assert llm_error.__name__ == "llm_error"


def test_core_self_healing_does_not_import_openai():
    """core should not import openai (split to llm/error_ui.py)"""
    import inspect

    from merco.core import self_healing
    src = inspect.getsource(self_healing)
    assert "openai" not in src.lower()
    assert "tool_error" not in src
    assert "classify_error" not in src
    assert "empty_response" not in src
    assert "llm_error" not in src
    assert "_is_retryable_llm_error" not in src
