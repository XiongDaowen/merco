"""merco LLM exception types.

Providers translate their SDK exceptions into these types so the agent and
error_ui never import an SDK. ``status_code`` is duck-typed by
``error_ui.classify_error``.

``llm_error`` is kept for backward compatibility with callers that still
import it from this module — it delegates to ``error_ui``.
"""
from __future__ import annotations

from merco.core.llm.error_ui import (  # noqa: F401
    classify_error,
    error_message,
    build_error_panel,
)


class ProviderError(Exception):
    """Base for all model-provider errors. Carries HTTP ``status_code`` (0 if unknown)."""

    def __init__(self, message: str = "", *, status_code: int = 0):
        super().__init__(message)
        self.status_code = status_code


class RateLimitError(ProviderError):
    """429 / rate limited."""


class AuthError(ProviderError):
    """401 / 403 / invalid credentials."""


class ConnectionError(ProviderError):  # noqa: A001 - intentional shadow for agent catch
    """Network / connection failure (no HTTP status)."""


class ModelNotFoundError(ProviderError):
    """404 / unknown model."""


def translate_openai_error(exc: Exception) -> ProviderError:
    """Translate an openai SDK exception into a merco ProviderError subclass."""
    import openai
    status = getattr(exc, "status_code", None) or 0
    if isinstance(exc, openai.AuthenticationError):
        return AuthError(str(exc), status_code=status or 401)
    if isinstance(exc, openai.RateLimitError):
        return RateLimitError(str(exc), status_code=status or 429)
    if isinstance(exc, openai.APIConnectionError):
        return ConnectionError(str(exc), status_code=0)
    if isinstance(exc, openai.NotFoundError):
        return ModelNotFoundError(str(exc), status_code=status or 404)
    if isinstance(exc, openai.APIStatusError):
        return ProviderError(str(exc), status_code=status)
    return ProviderError(str(exc), status_code=status)


def translate_anthropic_error(exc: Exception) -> ProviderError:
    """Translate an anthropic SDK exception into a merco ProviderError subclass."""
    import anthropic
    status = getattr(exc, "status_code", None) or 0
    if isinstance(exc, getattr(anthropic, "AuthenticationError", type(None))):
        return AuthError(str(exc), status_code=status or 401)
    if isinstance(exc, getattr(anthropic, "RateLimitError", type(None))):
        return RateLimitError(str(exc), status_code=status or 429)
    if isinstance(exc, getattr(anthropic, "APIConnectionError", type(None))):
        return ConnectionError(str(exc), status_code=0)
    if isinstance(exc, getattr(anthropic, "NotFoundError", type(None))):
        return ModelNotFoundError(str(exc), status_code=status or 404)
    if isinstance(exc, getattr(anthropic, "APIStatusError", type(None))):
        return ProviderError(str(exc), status_code=status)
    return ProviderError(str(exc), status_code=status)


def llm_error(exc: Exception) -> str:
    """Backward-compatible wrapper: convert an exception to a user-facing
    error message. Delegates to error_ui."""
    return error_message(classify_error(exc))
