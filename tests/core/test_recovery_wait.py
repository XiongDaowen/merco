"""Tests for WaitRecovery and ContextCompressRecovery error policies."""

import pytest

from merco.core.pipeline import RecoveryContext


class _FakeExc(Exception):
    def __init__(self, msg="err", status_code=None):
        super().__init__(msg)
        self.status_code = status_code


class TestWaitRecovery:
    @pytest.mark.asyncio
    async def test_retries_5xx_with_backoff(self):
        from merco.core.recovery.wait import WaitRecovery

        rec = WaitRecovery(delay=3.0, max_delay=30.0)
        ctx = RecoveryContext(error=_FakeExc("bad gateway", status_code=502))
        assert await rec.attempt(ctx) is True
        assert ctx.extra_wait == 3.0

        ctx2 = RecoveryContext(error=_FakeExc("bad gateway", status_code=502), attempt_count=1)
        assert await rec.attempt(ctx2) is True
        assert ctx2.extra_wait == 6.0

        ctx3 = RecoveryContext(error=_FakeExc("bad gateway", status_code=502), attempt_count=2)
        assert await rec.attempt(ctx3) is True
        assert ctx3.extra_wait == 12.0

    @pytest.mark.asyncio
    async def test_short_retry_401_only_once(self):
        from merco.core.recovery.wait import WaitRecovery

        rec = WaitRecovery(delay=3.0, max_delay=30.0)

        ctx = RecoveryContext(error=_FakeExc("unauthorized", status_code=401))
        assert await rec.attempt(ctx) is True
        assert ctx.extra_wait == 1.0

        ctx2 = RecoveryContext(error=_FakeExc("unauthorized", status_code=401), attempt_count=1)
        assert await rec.attempt(ctx2) is False

    @pytest.mark.asyncio
    async def test_404_only_short_retry_once(self):
        from merco.core.recovery.wait import WaitRecovery

        rec = WaitRecovery()
        ctx = RecoveryContext(error=_FakeExc("not found", status_code=404))
        assert await rec.attempt(ctx) is True
        assert ctx.extra_wait == 1.0
        ctx2 = RecoveryContext(error=_FakeExc("not found", status_code=404), attempt_count=1)
        assert await rec.attempt(ctx2) is False

    @pytest.mark.asyncio
    async def test_413_passes_to_compress(self):
        from merco.core.recovery.wait import WaitRecovery

        rec = WaitRecovery(delay=3.0)
        ctx = RecoveryContext(error=_FakeExc("too long", status_code=413))
        assert await rec.attempt(ctx) is False

    @pytest.mark.asyncio
    async def test_429_uses_default_backoff(self):
        from merco.core.recovery.wait import WaitRecovery

        rec = WaitRecovery(delay=3.0)
        ctx = RecoveryContext(error=_FakeExc("rate limit", status_code=429))
        assert await rec.attempt(ctx) is True
        assert ctx.extra_wait == 3.0

    @pytest.mark.asyncio
    async def test_connection_error_gets_backoff(self):
        from merco.core.recovery.wait import WaitRecovery

        rec = WaitRecovery(delay=3.0)

        class ConnErr(Exception):
            pass

        ctx = RecoveryContext(error=ConnErr("connection refused"))
        assert await rec.attempt(ctx) is True
        assert ctx.extra_wait == 3.0

    @pytest.mark.asyncio
    async def test_timeout_exception_gets_backoff(self):
        from merco.core.recovery.wait import WaitRecovery

        rec = WaitRecovery(delay=3.0)

        class TimeoutErr(Exception):
            pass

        ctx = RecoveryContext(error=TimeoutErr("read timeout"))
        assert await rec.attempt(ctx) is True
        assert ctx.extra_wait == 3.0

    @pytest.mark.asyncio
    async def test_backoff_capped_at_max_delay(self):
        from merco.core.recovery.wait import WaitRecovery

        rec = WaitRecovery(delay=3.0, max_delay=10.0)
        ctx = RecoveryContext(error=_FakeExc("err", status_code=500), attempt_count=10)
        assert await rec.attempt(ctx) is True
        assert ctx.extra_wait <= 10.0

    @pytest.mark.asyncio
    async def test_other_4xx_uses_shorter_backoff(self):
        from merco.core.recovery.wait import WaitRecovery

        rec = WaitRecovery(delay=3.0)
        ctx = RecoveryContext(error=_FakeExc("bad request", status_code=400))
        assert await rec.attempt(ctx) is True
        # base * 0.66 = 2.0 (approx)
        assert 1.5 <= ctx.extra_wait <= 2.5


class TestContextCompressRecovery:
    @pytest.mark.asyncio
    async def test_force_trigger_on_413(self):
        from merco.context.recovery import ContextCompressRecovery

        rec = ContextCompressRecovery()
        ctx = RecoveryContext(error=_FakeExc("too long", status_code=413), context_tokens=100)
        assert await rec.attempt(ctx) is True
        assert ctx.compress is True
        assert ctx.extra_wait >= 0.5

    @pytest.mark.asyncio
    async def test_force_trigger_on_too_long_keyword(self):
        from merco.context.recovery import ContextCompressRecovery

        rec = ContextCompressRecovery()
        ctx = RecoveryContext(error=Exception("maximum context length exceeded"), context_tokens=100)
        assert await rec.attempt(ctx) is True
        assert ctx.compress is True

    @pytest.mark.asyncio
    async def test_small_context_non_413_no_compress(self):
        from merco.context.recovery import ContextCompressRecovery

        rec = ContextCompressRecovery(min_context_bytes=30000)
        ctx = RecoveryContext(error=_FakeExc("err", status_code=500), context_tokens=100)
        assert await rec.attempt(ctx) is False

    @pytest.mark.asyncio
    async def test_large_context_compresses(self):
        from merco.context.recovery import ContextCompressRecovery

        rec = ContextCompressRecovery(min_context_bytes=30000)
        ctx = RecoveryContext(error=_FakeExc("err", status_code=500), context_tokens=100000)
        assert await rec.attempt(ctx) is True
        assert ctx.compress is True

    @pytest.mark.asyncio
    async def test_does_not_exceed_max_compress(self):
        from merco.context.recovery import ContextCompressRecovery

        rec = ContextCompressRecovery()
        ctx = RecoveryContext(error=_FakeExc("err", status_code=500), context_tokens=100000, compress_count=2)
        assert await rec.attempt(ctx) is False


class TestErrorsWrapper:
    def test_llm_error_delegates_to_error_message(self):
        from merco.core.llm.errors import llm_error

        exc = _FakeExc("bad gateway", status_code=502)
        msg = llm_error(exc)
        assert msg.startswith("❌ ")
        assert "502" in msg

    def test_is_retryable_llm_error_removed(self):
        import merco.core.llm.errors as errors_mod

        assert not hasattr(errors_mod, "_is_retryable_llm_error")
