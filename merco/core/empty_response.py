"""Empty response strategies."""
from __future__ import annotations

import logging
from .pipeline import EmptyResponseStrategy, EmptyResponseContext

logger = logging.getLogger("merco.pipeline")


class CallbackEmptyResponse(EmptyResponseStrategy):
    """空回复回调：注入 user 消息让 LLM 自愈。

    适用于支持 function calling 但偶尔忘记调用工具的模型。
    """

    name = "callback"

    async def attempt(self, ctx: EmptyResponseContext) -> bool:
        if ctx.retry_count >= ctx.max_retries:
            return False
        from merco.tools.errors import empty_response
        err = empty_response()
        ctx.inject_error = err["error"]
        return True
