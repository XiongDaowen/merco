"""LLM 调用错误处理 — 把 API 异常分类并脱敏。

边界：HTTP 状态码、关键字匹配脱敏、Retry 判定。不感知具体 provider 协议。
"""
from __future__ import annotations


def _is_retryable_llm_error(exc: Exception) -> bool:
    """判断 LLM API 错误是否可重试。

    按 HTTP 状态码大类判断（413 超长 + 429 限流 + 5xx 服务端），
    辅以错误消息关键字匹配覆盖非标准 provider。
    """
    try:
        from openai import APIStatusError
    except ImportError:
        return False
    if not isinstance(exc, APIStatusError):
        return False

    status = exc.status_code
    # 413 请求体过大 — 压缩后可重试
    if status == 413:
        return True
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
        "context length", "too long", "maximum context",
        "reduce the length", "prompt too long",
    ))


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
