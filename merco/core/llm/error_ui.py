"""LLM error UI helpers — classification, rendering, retry feedback.

Responsibility: what errors look like. NOT when to show them (callers decide).
Zero side effects: no logging, no SDK import (duck-typing only).
"""
from __future__ import annotations

import re
from contextlib import asynccontextmanager
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
    the exception class name. Uses duck-typing only (no SDK import).
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
    and truncate to max_len characters (appending '…' if truncated).

    兼容多种写法：
    - "api_key"、"api-key"、"API key"、"API Key"（下划线/连字符/空格）
    - "access_token"、"bearer_token"（下划线两侧都是词字母时也能命中）
    """
    msg = str(exc)

    for kw in _SENSITIVE_KEYWORDS:
        # 兼容 "api_key" / "api-key" / "API key" 等写法：
        # 把下划线视为可选空白（[ _-]?）。
        # 当前关键词仅含字母与下划线，无需 re.escape；
        # 如未来关键词含正则元字符，请改用 \Q...\E 包裹。
        #
        # 边界规则：用 (?<![a-zA-Z]) / (?![a-zA-Z]) 替代 \b。
        #   \b 会在 _ 处产生边界 → "access_token" 中 token 不会被匹配。
        #   字母边界不会在 _ 处产生边界 → "access_token" 命中；
        #   但 "tokens"（s 是字母）不会命中，因为 token 右邻 s 是字母。
        pattern_spaced = kw.replace("_", "[ _-]?")
        if re.search(rf'(?i)(?<![a-zA-Z]){pattern_spaced}(?![a-zA-Z])', msg):
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
    from rich.panel import Panel
    from rich.text import Text
    detail = sanitize_message(info.exc)
    text = Text.from_markup(
        f"[bold red]❌ {info.label}[/bold red]\n"
        f"[red]{info.hint}[/red]\n\n"
        f"[dim]{detail}[/dim]"
    )
    return Panel(
        text, border_style="red",
        title="⚠ API 错误", title_align="left", padding=(0, 1),
    )


def build_retry_line(info: ErrorInfo, attempt: int, max_attempts: int,
                     actions: list[str]) -> str:
    """Return a yellow one-line retry status string.

    Example: "↻ API 请求限流（第 1/3 次）— 等待 3s + 压缩上下文…"
    """
    action_str = " + ".join(actions) if actions else "立即重试"
    return (f"[yellow]↻ API {info.label}（第 {attempt}/{max_attempts} 次）"
            f"— {action_str}…[/yellow]")


@asynccontextmanager
async def retry_spinner(label: str, seconds: float, console):
    """Async context manager showing a transient spinner during a wait.

    Usage::

        async with retry_spinner("请求限流", 3.0, console):
            await asyncio.sleep(3.0)

    The spinner displays e.g. "⠋ 等待 2.3s 冷却中…" in yellow, updates at 8fps,
    and is transient (disappears on exit). If ``seconds <= 1`` it's a no-op
    (the wait is too short to justify a spinner).
    """
    import asyncio
    import itertools
    from rich.live import Live
    from rich.text import Text

    if seconds <= 1:
        yield
        return

    spinner = itertools.cycle("⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏")

    async def _tick(live, total):
        waited = 0.0
        try:
            while waited < total:
                await asyncio.sleep(0.1)
                waited += 0.1
                remain = max(0.0, total - waited)
                live.update(Text.from_markup(
                    f"[yellow]{next(spinner)} 等待 {remain:.1f}s 冷却中…[/yellow]"
                ))
        except asyncio.CancelledError:
            pass

    with Live(Text.from_markup(f"[yellow]{next(spinner)} 等待 {seconds:.1f}s 冷却中…[/yellow]"),
              console=console, refresh_per_second=8, transient=True) as live:
        ticker = asyncio.create_task(_tick(live, seconds))
        try:
            yield
        finally:
            ticker.cancel()
            try:
                await ticker
            except asyncio.CancelledError:
                pass


def error_message(info: ErrorInfo) -> str:
    """Return a Rich-markup string starting with "❌ " for the final error.

    Used as the agent's return value on terminal failure; the REPL detects
    startswith("❌") and wraps it in a red Panel via Text.from_markup.
    """
    detail = sanitize_message(info.exc)
    return (f"❌ [bold red]{info.label}[/bold red]：[red]{info.hint}[/red]\n"
            f"[dim]{detail}[/dim]")
