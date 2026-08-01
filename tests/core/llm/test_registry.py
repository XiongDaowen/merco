"""ModelRegistry - sole source of truth for providers + credential resolution."""

from unittest.mock import MagicMock

import pytest

from merco.core.config import ModelConfig
from merco.core.llm.base import ModelProviderInfo
from merco.core.llm.registry import ModelRegistry


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


def test_select_unknown_provider_with_base_url_falls_back_to_openai_compatible():
    """Wizard '自定义平台' path (I3 regression): a novel provider name + base_url
    is a custom OpenAI-compatible endpoint, not a typo -> select() falls back
    to OpenAICompatibleProvider instead of raising KeyError."""
    from merco.core.llm.openai_provider import OpenAICompatibleProvider

    reg = ModelRegistry()
    cfg = ModelConfig(
        provider="scnet",  # novel name, NOT in _BUILTIN_PROVIDERS
        model="scnet-xl",
        api_key="sk-custom",
        base_url="https://api.scnet.example.com/v1",
    )
    provider = reg.select(cfg)
    assert isinstance(provider, OpenAICompatibleProvider)
    assert provider.model == "scnet-xl"
    # custom base_url flows through to the underlying OpenAI client
    assert str(provider.client.base_url).rstrip("/") == "https://api.scnet.example.com/v1"


def test_select_known_builtin_still_works():
    """Regression guard: the try/except refactor in select() must not break the
    normal builtin path."""
    from merco.core.llm.openai_provider import OpenAICompatibleProvider

    reg = ModelRegistry()
    cfg = ModelConfig(provider="openai", model="gpt-4o", api_key="sk-test")
    provider = reg.select(cfg)
    assert isinstance(provider, OpenAICompatibleProvider)
    assert provider.model == "gpt-4o"


def test_register_third_party():
    reg = ModelRegistry()
    fake = MagicMock()
    info = ModelProviderInfo(name="gemini", provider_class=fake, display_name="Gemini")
    reg.register(info)
    assert reg.get("gemini") is info


def test_get_context_window_known_model():
    """已知 provider+model 返回窗口值"""
    from merco.core.llm.registry import ModelRegistry

    reg = ModelRegistry()
    assert reg.get_context_window("openai", "gpt-4o") == 128000
    assert reg.get_context_window("anthropic", "claude-sonnet-4-20250514") == 200000
    assert reg.get_context_window("deepseek", "deepseek-chat") == 64000


def test_get_context_window_unknown_returns_none():
    """未知 provider 或 model 返回 None"""
    from merco.core.llm.registry import ModelRegistry

    reg = ModelRegistry()
    assert reg.get_context_window("nonexistent", "gpt-4o") is None
    assert reg.get_context_window("openai", "not-a-model") is None


def test_get_context_window_plugin_registered():
    """插件注册的 provider 携带 context_windows 可查"""
    from merco.core.llm.base import ModelProviderInfo, ModelProvider
    from merco.core.llm.registry import ModelRegistry

    reg = ModelRegistry()
    reg.register(ModelProviderInfo(
        name="mymodel", provider_class=ModelProvider, display_name="M",
        models=["my-model"], context_windows={"my-model": 200000},
    ))
    assert reg.get_context_window("mymodel", "my-model") == 200000
