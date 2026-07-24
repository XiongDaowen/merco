"""可扩展错误处理 — 注册自定义异常 handler。

边界：仅作为异常 handler 注册表。工具错误走 merco.tools.errors，LLM 错误走 merco.core.llm.errors。
"""
from __future__ import annotations

import logging
from collections.abc import Callable

logger = logging.getLogger("merco.self_healing")


_extra_handlers: dict[type, Callable] = {}


def register_handler(exc_type: type, handler: Callable) -> None:
    """注册自定义异常处理器。

    handler 签名: (exc, tool_name, tool_schema) -> dict | None
    返回 None 表示不处理，走默认逻辑。
    """
    _extra_handlers[exc_type] = handler


def _apply_custom_handlers(
    exc: Exception, tool_name: str, tool_schema: dict | None,
) -> dict | None:
    """依次尝试注册的自定义 handler"""
    for exc_type, handler in _extra_handlers.items():
        if isinstance(exc, exc_type):
            try:
                return handler(exc, tool_name, tool_schema)
            except Exception:
                logger.warning("自定义 handler 异常", exc_info=True)
    return None
