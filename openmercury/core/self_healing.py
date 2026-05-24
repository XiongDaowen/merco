"""错误自愈器 — 统一处理异常，产出 LLM 可读的结构化错误

设计原则：
- 所有异常都转为结构化 dict，让 LLM 看到清晰的错误信息后自行纠正
- 每个错误带 suggestion 字段，告诉 LLM 如何修正
- 异常类型通过 register_handler() 扩展，不对具体异常硬编码
- 未知异常兜底：记录日志，返回精简的公开错误（不泄漏内部细节）
"""

import logging
from typing import Any, Callable

logger = logging.getLogger("openmercury.self_healing")

# ── 错误分类 ────────────────────────────────────────────

# 对 LLM 友好的错误分类
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
    """将异常映射到错误类别，用于日志和统计"""
    if isinstance(exc, TypeError):
        return "param_mismatch"
    if isinstance(exc, TimeoutError):
        return "timeout"
    # 子类优先 —— PermissionError / FileNotFoundError 是 OSError 的子类
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


# ── 核心函数 ────────────────────────────────────────────

def tool_error(
    exc: Exception,
    tool_name: str,
    tool_schema: dict | None = None,
) -> dict:
    """将工具执行异常转为 LLM 可读的结构化错误。

    Args:
        exc: 原始异常
        tool_name: 出错的工具名
        tool_schema: 工具的 parameters schema（用于提供 params hint）

    Returns:
        dict，包含 error / suggestion / category 等字段，LLM 可直接消费
    """
    category = classify_error(exc)
    label = ERROR_CATEGORIES.get(category, "未知错误")

    # 基础结构：所有错误都有这些字段
    result: dict[str, Any] = {
        "error": f"[{label}] {tool_name}: {_public_message(exc)}",
        "category": category,
        "tool": tool_name,
    }

    # 按类别补充 suggestion
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
        # 未知异常：对 LLM 友好但不泄漏内部信息
        result["suggestion"] = "执行时发生意外错误。请尝试其他方式完成用户请求。"
        # 完整堆栈记日志
        logger.warning("工具 %s 未知异常", tool_name, exc_info=True)

    return result


def _is_retryable_llm_error(exc: Exception) -> bool:
    """判断 LLM API 错误是否可重试。

    按 HTTP 状态码大类判断（429 限流 + 5xx 服务端），
    辅以错误消息关键字匹配覆盖非标准 provider。
    """
    try:
        from openai import APIStatusError
    except ImportError:
        return False
    if not isinstance(exc, APIStatusError):
        return False

    status = exc.status_code
    # 429 限流 — 所有 provider 通用
    if status == 429:
        return True
    # 5xx 服务端错误 — 所有 provider 通用
    if 500 <= status <= 599:
        return True
    # 关键字兜底：部分 provider 用 4xx 返回临时错误
    body = str(exc).lower()
    return any(kw in body for kw in (
        "rate limit", "too many requests", "overloaded",
        "capacity", "throttl", "temporarily unavailable",
    ))


def empty_response() -> dict:
    """空回复错误 — 回调 LLM 让它产出实际内容。

    模型返回了 thinking 但没有 content 也没有 tool_calls 时使用。
    以 user 消息注入上下文，LLM 看到后会自愈。
    """
    return {
        "error": "[空回复] 你既没有回复用户也没有调用工具。"
                 "请直接回答用户，或使用工具推进任务。",
        "category": "empty_response",
        "suggestion": "请直接回复用户，或调用工具获取信息。",
    }


def llm_error(exc: Exception) -> str:
    """将 LLM 调用异常转为对用户友好的错误消息。

    不在返回消息中泄漏 API key、内部堆栈等敏感信息。
    """
    msg = str(exc)
    # 常见敏感信息：截掉 key/secret/token 等字段
    for keyword in ("api_key", "token", "secret", "key", "authorization"):
        if keyword.lower() in msg.lower():
            msg = "(包含敏感信息，已脱敏)"
            break

    return f"模型调用失败，请检查 API key 和网络连接。（{msg}）"


# ── 内部工具函数 ─────────────────────────────────────────

def _public_message(exc: Exception) -> str:
    """提取异常的公开消息，截断防止过长注入"""
    msg = str(exc)
    if len(msg) > 300:
        msg = msg[:300] + "..."
    return msg


def _params_hint(schema: dict | None) -> str:
    """生成参数提示"""
    if not schema:
        return "请检查工具调用参数。"
    names = _param_names(schema)
    required = schema.get("required", [])
    if required:
        return f"必需: {', '.join(required)}。可用: {', '.join(names)}。"
    return f"可用参数: {', '.join(names)}。"


def _param_names(schema: dict) -> list[str]:
    """从 schema 提取参数名列表"""
    props = schema.get("properties", {})
    return list(props.keys()) if isinstance(props, dict) else []


# ── 注册新 handler ───────────────────────────────────────

# 可扩展的 handler 注册表：异常类型 → 自定义处理函数
# 使用方式：register_handler(MyCustomError, lambda exc, tool, schema: {...})
_extra_handlers: dict[type, Callable] = {}


def register_handler(exc_type: type, handler: Callable):
    """注册自定义异常处理器。

    handler 签名: (exc, tool_name, tool_schema) -> dict | None
    返回 None 表示不处理，走默认逻辑。
    """
    _extra_handlers[exc_type] = handler


def _apply_custom_handlers(exc: Exception, tool_name: str, tool_schema: dict | None) -> dict | None:
    """依次尝试注册的自定义 handler"""
    for exc_type, handler in _extra_handlers.items():
        if isinstance(exc, exc_type):
            try:
                return handler(exc, tool_name, tool_schema)
            except Exception:
                logger.warning("自定义 handler 异常", exc_info=True)
    return None
