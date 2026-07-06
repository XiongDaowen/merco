"""ModelFallbackRecovery — switches to a fallback model on failure."""
from __future__ import annotations

import logging
from merco.core.pipeline import Recovery, RecoveryContext

logger = logging.getLogger("merco.pipeline")


class ModelFallbackRecovery(Recovery):
    """模型降级：当前模型不可用时切换到备选 [框架预留]

    需要 Agent 支持 switch_model 标志位后启用。
    """

    name = "model_fallback"

    def __init__(self, fallback_model: str = ""):
        self.fallback_model = fallback_model

    async def attempt(self, ctx: RecoveryContext) -> bool:
        if not self.fallback_model:
            return False
        ctx.switch_model = self.fallback_model
        return True
