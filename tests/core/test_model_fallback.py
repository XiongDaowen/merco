"""ModelFallbackRecovery - cross-provider fallback via ModelConfig."""

import pytest

from merco.core.config import ModelConfig
from merco.core.pipeline import RecoveryContext
from merco.core.recovery.model_fallback import ModelFallbackRecovery


@pytest.mark.asyncio
async def test_fallback_sets_switch_model_to_modelconfig():
    fb = ModelConfig(provider="anthropic", model="claude-sonnet-4-20250514")
    recovery = ModelFallbackRecovery(fallbacks=[fb])
    ctx = RecoveryContext(error=RuntimeError("boom"))
    assert await recovery.attempt(ctx) is True
    assert isinstance(ctx.switch_model, ModelConfig)
    assert ctx.switch_model.provider == "anthropic"


@pytest.mark.asyncio
async def test_fallback_chain_advances_cursor():
    fb1 = ModelConfig(provider="anthropic", model="c1")
    fb2 = ModelConfig(provider="deepseek", model="d1")
    recovery = ModelFallbackRecovery(fallbacks=[fb1, fb2])
    ctx = RecoveryContext(error=RuntimeError("boom"))
    await recovery.attempt(ctx)
    assert ctx.switch_model.model == "c1"
    await recovery.attempt(ctx)
    assert ctx.switch_model.model == "d1"


@pytest.mark.asyncio
async def test_no_fallbacks_returns_false():
    recovery = ModelFallbackRecovery(fallbacks=[])
    ctx = RecoveryContext(error=RuntimeError("boom"))
    assert await recovery.attempt(ctx) is False
