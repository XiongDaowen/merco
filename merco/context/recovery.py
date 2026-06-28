"""ContextCompressRecovery — compresses context when request body is too large."""
from __future__ import annotations

import logging
from merco.core.pipeline import Recovery, RecoveryContext, _is_retryable

logger = logging.getLogger("merco.pipeline")


class ContextCompressRecovery(Recovery):
    """压缩上下文：请求体过大触发 429 时的核心恢复手段"""

    name = "compress_context"

    def __init__(self, min_context_bytes: int = 30000):
        # 低于此大小不压缩（压缩有损，尽量不碰）
        self.min_context_bytes = min_context_bytes

    async def attempt(self, ctx: RecoveryContext) -> bool:
        if not _is_retryable(ctx):
            return False
        if ctx.compress_count >= ctx.max_compress:
            return False
        # 动态判断：上下文 < min 时可能只是瞬时限流，让 WaitRecovery 处理
        if ctx.context_tokens > 0 and ctx.context_tokens * 4 < self.min_context_bytes:
            return False  # 上下文很小，压缩无意义
        logger.info("→ 压缩上下文后重试 LLM（第 %d/%d 次）",
                     ctx.compress_count + 1, ctx.max_compress)
        ctx.compress = True
        return True
