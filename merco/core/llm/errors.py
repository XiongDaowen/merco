"""LLM error helpers — thin wrappers around error_ui.

Kept for backward compatibility; new code should use
``merco.core.llm.error_ui`` directly.
"""
from __future__ import annotations

from merco.core.llm.error_ui import (  # noqa: F401
    ErrorInfo,
    classify_error,
    sanitize_message,
    build_error_panel,
    build_retry_line,
    retry_spinner,
    error_message,
)


def llm_error(exc: Exception) -> str:
    """Backward-compatible wrapper: convert an exception to a user-facing
    error message. Delegates to error_ui."""
    return error_message(classify_error(exc))
