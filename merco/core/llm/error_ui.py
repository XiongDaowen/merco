"""LLM error UI helpers — classification, rendering, retry feedback.

Responsibility: what errors look like. NOT when to show them (callers decide).
Zero side effects: no logging, no openai import (duck-typing only).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import AsyncIterator


_SENSITIVE_KEYWORDS = ("api_key", "token", "secret", "authorization", "bearer")


@dataclass
class ErrorInfo:
    """Classified error metadata."""
    label: str   # Short label e.g. "认证失败", "服务端错误 (502)"
    hint: str    # One-line user-facing hint
    exc: Exception  # Original exception


def classify_error(exc: Exception) -> ErrorInfo:
    """Classify an exception into ErrorInfo using duck-typing.

    Reads ``exc.status_code`` if present; falls back to scanning str(exc) and
    the exception class name. Does NOT import openai.
    """
    status = getattr(exc, "status_code", None)
    body = str(exc).lower()
    name = type(exc).__name__

    # 401 / unauthorized / invalid/expired api key
    if (
        status == 401
        or "unauthorized" in body
        or "authentication" in body
        or ("api key" in body and ("invalid" in body or "expired" in body))
    ):
        return ErrorInfo(label="认证失败", hint="API Key 无效或已过期，请检查配置。", exc=exc)

    # 403 / forbidden / permission
    if (
        status == 403
        or "forbidden" in body
        or "permission" in body
        or "access denied" in body
    ):
        return ErrorInfo(label="权限不足", hint="账户无权限访问该资源。", exc=exc)

    # 404 / model not found
    if (
        status == 404
        or ("not found" in body and "model" in body)
        or "model not exist" in body
    ):
        return ErrorInfo(label="模型/接口不存在", hint="模型或接口不存在，检查模型名和 base_url。", exc=exc)

    # 413 / context length
    if (
        status == 413
        or "context length" in body
        or "maximum context" in body
        or "prompt too long" in body
        or "too long" in body
    ):
        return ErrorInfo(label="请求过长", hint="上下文超过模型上限，正在压缩后重试…", exc=exc)

    # 429 / rate limit
    if (
        status == 429
        or "rate limit" in body
        or "too many requests" in body
    ):
        return ErrorInfo(label="请求限流", hint="API 限流，稍后重试…", exc=exc)

    # 5xx server errors
    if isinstance(status, int) and 500 <= status <= 599:
        return ErrorInfo(label=f"服务端错误 ({status})", hint="API 服务器异常，稍后重试…", exc=exc)

    # 408 timeout
    if isinstance(status, int) and status == 408:
        return ErrorInfo(label="请求超时", hint="API 请求超时，稍后重试…", exc=exc)

    # Timeout by class name or body
    if "timeout" in name.lower() or "timeout" in body or "timed out" in body:
        return ErrorInfo(label="请求超时", hint="API 响应超时，稍后重试…", exc=exc)

    # Connection errors
    if "connection" in name.lower() or "connect" in body or "network" in body:
        return ErrorInfo(label="连接错误", hint="无法连接到 API 服务器，请检查网络或 base_url。", exc=exc)

    # Other 4xx client errors
    if isinstance(status, int) and 400 <= status < 500:
        return ErrorInfo(label=f"请求错误 ({status})", hint="请求被服务端拒绝，稍后重试…", exc=exc)

    # Fallback: class name or generic label
    label = name or "调用失败"
    return ErrorInfo(label=label, hint="API 调用失败，稍后重试…", exc=exc)


def sanitize_message(exc: Exception, max_len: int = 300) -> str:
    """Redact sensitive keywords (api_key/token/secret/authorization/bearer)
    and truncate to max_len characters (appending '…' if truncated)."""
    msg = str(exc)
    low = msg.lower()

    for kw in _SENSITIVE_KEYWORDS:
        if kw in low:
            return "(包含敏感信息，已脱敏)"

    if len(msg) > max_len:
        return msg[:max_len].rstrip() + "…"

    return msg


def build_error_panel(info: ErrorInfo):
    """Return a Rich Panel for an error. Red border, title '⚠ API 错误'.

    Layout:
      ❌ <label> (bold red)
      <hint> (red)
      <blank line>
      <sanitized detail> (dim)
    """
    raise NotImplementedError


def build_retry_line(info: ErrorInfo, attempt: int, max_attempts: int,
                     actions: list[str]) -> str:
    """Return a yellow one-line retry status string.

    Example: "↻ API 请求限流（第 1/3 次）— 等待 3s + 压缩上下文…"
    """
    raise NotImplementedError


def retry_spinner(label: str, seconds: float, console):
    """Async context manager showing a transient spinner during a wait.

    Usage::

        async with retry_spinner("请求限流", 3.0, console):
            await asyncio.sleep(3.0)

    The spinner displays e.g. "⠋ 等待 2.3s 冷却中…" in yellow, updates at 8fps,
    and is transient (disappears on exit). If ``seconds <= 1`` it's a no-op
    (the wait is too short to justify a spinner).
    """
    raise NotImplementedError


def error_message(info: ErrorInfo) -> str:
    """Return a Rich-markup string starting with "❌ " for the final error.

    Used as the agent's return value on terminal failure; the REPL detects
    startswith("❌") and wraps it in a red Panel via Text.from_markup.
    """
    raise NotImplementedError
