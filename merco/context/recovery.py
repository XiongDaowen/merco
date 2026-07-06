"""ContextCompressRecovery — compresses context when request body is too large."""
from __future__ import annotations

import logging
from merco.core.pipeline import Recovery, RecoveryContext

logger = logging.getLogger("merco.pipeline")


class ContextCompressRecovery(Recovery):
    """Compress context: triggered by 413/too-long keywords OR large context."""

    name = "compress_context"

    def __init__(self, min_context_bytes: int = 30000):
        self.min_context_bytes = min_context_bytes

    async def attempt(self, ctx: RecoveryContext) -> bool:
        if ctx.compress_count >= ctx.max_compress:
            return False

        status = getattr(ctx.error, "status_code", None)
        body = str(ctx.error).lower()

        # Force trigger on explicit too-long errors, even for small contexts.
        force = (
            status == 413
            or "context length" in body
            or "maximum context" in body
            or "prompt too long" in body
            or ("too long" in body and "context" in body)
        )

        if not force:
            if ctx.context_tokens > 0 and \
                    ctx.context_tokens * 4 < self.min_context_bytes:
                return False

        logger.info("→ 压缩上下文后重试 LLM（第 %d/%d 次）",
                     ctx.compress_count + 1, ctx.max_compress)
        ctx.compress = True
        ctx.extra_wait = max(ctx.extra_wait, 0.5)
        return True
