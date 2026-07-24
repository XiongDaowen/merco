"""ModelRegistry - sole source of truth for model providers.

_BUILTIN_PROVIDERS is declarative data feeding the registry (not a static dict
of provider metadata). Third-party providers register at runtime via
PluginContext.register_model_provider.
"""
from __future__ import annotations

import os

from merco.core.llm.base import ModelProvider, ModelProviderInfo
from merco.core.llm.openai_provider import OpenAICompatibleProvider
from merco.core.llm.anthropic_provider import AnthropicNativeProvider


_BUILTIN_PROVIDERS: list[ModelProviderInfo] = [
    ModelProviderInfo(
        name="openai", provider_class=OpenAICompatibleProvider, display_name="OpenAI",
        base_url="https://api.openai.com/v1", key_env="OPENAI_API_KEY",
        key_help="https://platform.openai.com/api-keys", default_model="gpt-4o",
        models=["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "o3-mini", "o1"],
        description="最通用的平台，GPT-4o / o3 系列",
    ),
    ModelProviderInfo(
        name="minimax", provider_class=OpenAICompatibleProvider, display_name="MiniMax",
        base_url="https://api.minimaxi.com/v1", key_env="MINIMAX_API_KEY",
        key_help="https://platform.minimaxi.com/user-center/basic-information",
        default_model="MiniMax-M2.7",
        models=["MiniMax-M2.7", "MiniMax-Text-01", "abab7-chat"],
        description="国产平台，MiniMax-M2.7 性价比高",
    ),
    ModelProviderInfo(
        name="anthropic", provider_class=AnthropicNativeProvider, display_name="Anthropic",
        base_url="https://api.anthropic.com", key_env="ANTHROPIC_API_KEY",
        key_help="https://console.anthropic.com/settings/keys",
        default_model="claude-sonnet-4-20250514",
        models=["claude-sonnet-4-20250514", "claude-3-5-haiku-20241022",
                "claude-3-opus-20240229", "claude-3-5-sonnet-20241022"],
        description="Claude 系列，代码能力优秀（原生 Messages API）",
    ),
    ModelProviderInfo(
        name="openrouter", provider_class=OpenAICompatibleProvider, display_name="OpenRouter",
        base_url="https://openrouter.ai/api/v1", key_env="OPENROUTER_API_KEY",
        key_help="https://openrouter.ai/keys", default_model="anthropic/claude-sonnet-4",
        models=[], description="模型聚合平台，一个 key 调用上百种模型",
    ),
    ModelProviderInfo(
        name="deepseek", provider_class=OpenAICompatibleProvider, display_name="DeepSeek",
        base_url="https://api.deepseek.com/v1", key_env="DEEPSEEK_API_KEY",
        key_help="https://platform.deepseek.com/api_keys", default_model="deepseek-chat",
        models=["deepseek-chat", "deepseek-reasoner"],
        description="国产平台，deepseek-reasoner 推理能力强",
    ),
]


class ModelRegistry:
    """Sole source of truth: register/get/list/select. Owns credential resolution."""

    def __init__(self):
        self._providers: dict[str, ModelProviderInfo] = {
            p.name: p for p in _BUILTIN_PROVIDERS
        }

    def register(self, info: ModelProviderInfo) -> None:
        self._providers[info.name] = info

    def get(self, name: str) -> ModelProviderInfo:
        if name not in self._providers:
            raise KeyError(f"Unknown model provider: {name!r}")
        return self._providers[name]

    def list(self) -> list[ModelProviderInfo]:
        return list(self._providers.values())

    def select(self, model_config) -> ModelProvider:
        """Resolve credentials (config > env > info defaults) + build provider.

        An unknown provider name WITH a configured base_url is treated as a
        custom OpenAI-compatible endpoint (setup wizard '自定义平台' path: the
        wizard writes a novel provider name + base_url for an OpenAI-compatible
        service). Without a base_url, an unknown name is a genuine typo /
        misconfiguration and still raises KeyError.
        """
        try:
            info = self.get(model_config.provider)
        except KeyError:
            if not model_config.base_url:
                raise  # unknown provider + no base_url = typo / misconfiguration
            # Custom OpenAI-compatible endpoint (wizard '自定义平台' path):
            # no info defaults available, build directly from config.
            return OpenAICompatibleProvider(
                api_key=model_config.api_key or "",
                model=model_config.model,
                base_url=model_config.base_url,
                temperature=model_config.temperature,
                max_tokens=model_config.max_tokens,
                cooldown=getattr(model_config, "request_cooldown", 0),
                extra_params=model_config.extra_params,
                headers=model_config.headers,
            )
        api_key = model_config.api_key or os.environ.get(info.key_env, "")
        base_url = model_config.base_url or info.base_url
        return info.provider_class(
            api_key=api_key,
            model=model_config.model,
            base_url=base_url,
            temperature=model_config.temperature,
            max_tokens=model_config.max_tokens,
            cooldown=getattr(model_config, "request_cooldown", 0),
            extra_params=model_config.extra_params,
            headers=model_config.headers,
        )
