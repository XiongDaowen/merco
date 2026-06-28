"""工具执行错误处理 — 把异常转为 LLM 可消费的结构化 dict。

边界：错误分类 + 公共消息脱敏。LLM 错误（APIStatusError 等）由 core.llm.errors 处理。
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("merco.tools.errors")


ERROR_CATEGORIES = {
    "param_mismatch": "参数不匹配",
    "tool_not_found": "工具不存在",
    "timeout": "执行超时",
    "permission": "权限不足",
    "network": "网络错误",
    "resource_not_found": "资源不存在",
    "internal": "内部错误",
    "unknown": "未知错误",
}


def classify_error(exc: Exception) -> str:
    """将异常映射到错误类别"""
    if isinstance(exc, TypeError):
        return "param_mismatch"
    if isinstance(exc, TimeoutError):
        return "timeout"
    if isinstance(exc, PermissionError):
        return "permission"
    if isinstance(exc, FileNotFoundError):
        return "resource_not_found"
    if isinstance(exc, ConnectionError):
        return "network"
    if isinstance(exc, OSError):
        return "network"
    if isinstance(exc, ValueError):
        return "param_mismatch"
    return "unknown"


def tool_error(
    exc: Exception,
    tool_name: str,
    tool_schema: dict | None = None,
) -> dict:
    """将工具执行异常转为 LLM 可读的结构化错误"""
    category = classify_error(exc)
    label = ERROR_CATEGORIES.get(category, "未知错误")
    result: dict[str, Any] = {
        "error": f"[{label}] {tool_name}: {_public_message(exc)}",
        "category": category,
        "tool": tool_name,
    }
    if category == "param_mismatch":
        hint = _params_hint(tool_schema)
        result["suggestion"] = f"参数类型或值不正确。{hint}"
        if tool_schema:
            result["available_params"] = _param_names(tool_schema)
    elif category == "tool_not_found":
        result["suggestion"] = "该工具不可用。请使用其他可用工具完成用户请求。"
    elif category == "timeout":
        result["suggestion"] = "操作超时。可尝试减少数据量、拆分请求，或使用其他工具。"
    elif category == "permission":
        result["suggestion"] = "权限不足。请检查文件权限，或使用其他路径/工具。"
    elif category == "network":
        result["suggestion"] = "网络请求失败。可重试，或检查 URL 是否正确。"
    elif category == "resource_not_found":
        result["suggestion"] = "资源（文件/路径）不存在。请检查路径拼写，或搜索确认位置。"
    else:
        result["suggestion"] = "执行时发生意外错误。请尝试其他方式完成用户请求。"
        logger.warning("工具 %s 未知异常", tool_name, exc_info=True)
    return result


def empty_response() -> dict:
    """空回复错误 — 回调 LLM 让它产出实际内容"""
    return {
        "error": "[空回复] 你既没有回复用户也没有调用工具。"
                 "请直接回答用户，或使用工具推进任务。",
        "category": "empty_response",
        "suggestion": "请直接回复用户，或调用工具获取信息。",
    }


def _public_message(exc: Exception) -> str:
    msg = str(exc)
    if len(msg) > 300:
        msg = msg[:300] + "..."
    return msg


def _params_hint(schema: dict | None) -> str:
    if not schema:
        return "请检查工具调用参数。"
    names = _param_names(schema)
    required = schema.get("required", [])
    if required:
        return f"必需: {', '.join(required)}。可用: {', '.join(names)}。"
    return f"可用参数: {', '.join(names)}。"


def _param_names(schema: dict) -> list[str]:
    props = schema.get("properties", {})
    return list(props.keys()) if isinstance(props, dict) else []
