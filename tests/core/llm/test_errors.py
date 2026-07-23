"""merco LLM exception types - provider-translated, SDK-agnostic."""
import pytest
from merco.core.llm.errors import (
    ProviderError, RateLimitError, AuthError, ConnectionError,
)
from merco.core.llm.openai_provider import translate_openai_error


def test_provider_error_carries_status_code():
    err = ProviderError("boom", status_code=429)
    assert err.status_code == 429
    assert str(err) == "boom"


def test_subclasses_are_provider_errors():
    assert issubclass(RateLimitError, ProviderError)
    assert issubclass(AuthError, ProviderError)
    assert issubclass(ConnectionError, ProviderError)


def test_translate_openai_429():
    import httpx
    import openai
    from openai import RateLimitError as OAIRateLimit
    # Construct a real openai RateLimitError requires a response with a request attached.
    req = httpx.Request("POST", "http://example.com")
    resp = httpx.Response(429, request=req)
    try:
        raise OAIRateLimit("too many", response=resp, body=None)
    except OAIRateLimit as e:
        translated = translate_openai_error(e)
        assert isinstance(translated, RateLimitError)
        assert translated.status_code == 429


def test_translate_openai_401():
    import httpx
    from openai import AuthenticationError
    req = httpx.Request("POST", "http://example.com")
    resp = httpx.Response(401, request=req)
    try:
        raise AuthenticationError("bad key", response=resp, body=None)
    except AuthenticationError as e:
        translated = translate_openai_error(e)
        assert isinstance(translated, AuthError)
        assert translated.status_code == 401
