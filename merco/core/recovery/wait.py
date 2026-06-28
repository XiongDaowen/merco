"""WaitRecovery — delays before retry on transient 429/5xx errors."""
from __future__ import annotations

import logging
from merco.core.pipeline import Recovery, RecoveryContext, _is_retryable

logger = logging.getLogger("merco.pipeline")


class WaitRecovery(Recovery):
    """等待：瞬时 429/5xx 给网关冷却窗口"""

    name = "wait"

    def __init__(self, delay: float = 3.0, max_delay: float = 30.0):
        self.delay = delay
        self.max_delay = max_delay

    async def attempt(self, ctx: RecoveryContext) -> bool:
        if not _is_retryable(ctx):
            return False
        # 413 等待没用，跳过让 ContextCompressRecovery 压缩
        if ctx.status_code == 413:
            return False
        # 动态退避：每次重试翻倍，上限 max_delay
        delay = min(self.delay * (2 ** ctx.attempt_count), self.max_delay)
        logger.info("→ 等待 %.1fs 后重试 LLM…", delay)
        ctx.extra_wait = max(ctx.extra_wait, delay)
        return True
