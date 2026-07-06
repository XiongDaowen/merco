"""LLM error UI helpers — classification, rendering, retry feedback.

Responsibility: what errors look like. NOT when to show them (callers decide).
Zero side effects: no logging, no openai import (duck-typing only).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import AsyncIterator


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
    raise NotImplementedError


def sanitize_message(exc: Exception, max_len: int = 300) -> str:
    """Redact sensitive keywords (api_key/token/secret/authorization/bearer)
    and truncate to max_len characters (appending '…' if truncated)."""
    raise NotImplementedError


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
