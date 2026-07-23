"""ModelRegistry - sole source of truth for providers + credential resolution."""
import pytest
from unittest.mock import MagicMock
from merco.core.llm.registry import ModelRegistry, _BUILTIN_PROVIDERS
from merco.core.llm.base import ModelProviderInfo
from merco.core.config import ModelConfig


def test_builtin_providers_seeded():
    reg = ModelRegistry()
    names = {p.name for p in reg.list()}
    assert {"openai", "minimax", "anthropic", "openrouter", "deepseek"} <= names


def test_builtin_anthropic_uses_native_provider_class():
    reg = ModelRegistry()
    from merco.core.llm.anthropic_provider import AnthropicNativeProvider
    info = reg.get("anthropic")
    assert info.provider_class is AnthropicNativeProvider
    assert info.base_url == "https://api.anthropic.com"


def test_select_resolves_credentials_config_over_env(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "env-key")
    reg = ModelRegistry()
    cfg = ModelConfig(provider="openai", model="gpt-4o", api_key="cfg-key")
    provider = reg.select(cfg)
    assert provider.model == "gpt-4o"
    # api_key resolved from config (takes priority over env)
    assert provider.client.api_key == "cfg-key"


def test_select_resolves_credentials_from_env(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "env-key")
    reg = ModelRegistry()
    cfg = ModelConfig(provider="openai", model="gpt-4o")  # no api_key
    provider = reg.select(cfg)
    assert provider.client.api_key == "env-key"


def test_select_unknown_provider_raises():
    reg = ModelRegistry()
    cfg = ModelConfig(provider="nope", model="x")
    with pytest.raises(KeyError):
        reg.select(cfg)


def test_register_third_party():
    reg = ModelRegistry()
    Fake = MagicMock()
    info = ModelProviderInfo(name="gemini", provider_class=Fake, display_name="Gemini")
    reg.register(info)
    assert reg.get("gemini") is info
