"""ModelFallbackRecovery - cross-provider fallback on failure."""

from __future__ import annotations

from merco.core.pipeline import Recovery, RecoveryContext


class ModelFallbackRecovery(Recovery):
    """模型降级：失败时按 fallback 链切换到备选 ModelConfig（可跨 provider）。"""

    name = "model_fallback"

    def __init__(self, fallbacks: list | None = None):
        self.fallbacks = list(fallbacks or [])
        self._cursor = 0

    async def attempt(self, ctx: RecoveryContext) -> bool:
        if self._cursor >= len(self.fallbacks):
            return False
        ctx.switch_model = self.fallbacks[self._cursor]
        self._cursor += 1
        return True
