"""WaitRecovery — delays before retry on errors.

Differentiated wait:
- 429/5xx/network/timeout: exponential backoff starting at `delay`, capped at `max_delay`
- 413/context-length: returns False (let ContextCompressRecovery handle)
- 401/403/404: one short 1.0s retry, then gives up
- Other 4xx/unknown: backoff starting at delay*0.66 (slightly shorter)
"""
from __future__ import annotations

import logging

from merco.core.pipeline import Recovery, RecoveryContext

logger = logging.getLogger("merco.pipeline")

# Status codes that are deterministic (wrong config) — fast retry once, then stop.
SHORT_RETRY_STATUSES = frozenset({401, 403, 404})


class WaitRecovery(Recovery):
    """Wait before retry; differentiated policy by error type."""

    name = "wait"

    def __init__(self, delay: float = 3.0, max_delay: float = 30.0,
                 short_delay: float = 1.0):
        self.delay = delay
        self.max_delay = max_delay
        self.short_delay = short_delay

    async def attempt(self, ctx: RecoveryContext) -> bool:
        status = getattr(ctx.error, "status_code", None)
        body = str(ctx.error).lower()
        name = type(ctx.error).__name__.lower()

        # 413/too-long → compression handles it
        if status == 413 or "context length" in body or "maximum context" in body \
                or "prompt too long" in body \
                or ("too long" in body and "context" in body):
            return False

        # Deterministic errors: one short retry only
        if status in SHORT_RETRY_STATUSES:
            if ctx.attempt_count >= 1:
                return False
            delay = self.short_delay
            logger.info("→ 确定性错误 (status=%s)，快速重试一次（%.1fs）",
                        status, delay)
            ctx.extra_wait = max(ctx.extra_wait, delay)
            return True

        # Network/timeout detection
        is_network = (
            "connection" in name
            or "timeout" in name
            or "connect" in body
            or "timeout" in body
            or "timed out" in body
            or "network" in body
        )

        # Pick base delay
        is_5xx = isinstance(status, int) and 500 <= status <= 599
        is_429 = status == 429 or "rate limit" in body or "too many requests" in body
        if is_5xx or is_429 or is_network:
            base = self.delay
        elif isinstance(status, int) and 400 <= status < 500:
            base = self.delay * 0.66
        else:
            base = self.delay * 0.66

        delay = min(base * (2 ** ctx.attempt_count), self.max_delay)
        logger.info("→ 等待 %.1fs 后重试 LLM（attempt=%d, status=%s）",
                    delay, ctx.attempt_count + 1, status)
        ctx.extra_wait = max(ctx.extra_wait, delay)
        return True
