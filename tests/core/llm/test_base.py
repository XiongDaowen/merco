"""ModelProvider ABC + ModelProviderInfo."""

import pytest

from merco.core.llm.base import ModelProvider, ModelProviderInfo


def test_cannot_instantiate_abc():
    with pytest.raises(TypeError):
        ModelProvider()


def test_model_provider_info_defaults():
    class FakeProvider(ModelProvider):
        name = "fake"

        async def chat(self, messages, tools=None, tool_choice=None):
            return {}

        def chat_stream(self, messages, tools=None, tool_choice=None):
            yield {}

    info = ModelProviderInfo(name="fake", provider_class=FakeProvider, display_name="Fake")
    assert info.base_url == ""
    assert info.models == []
    assert info.provider_class is FakeProvider


def test_model_provider_info_strict_superset_no_dict_compat():
    info = ModelProviderInfo(name="x", provider_class=ModelProvider, display_name="X")
    with pytest.raises(TypeError):
        info["base_url"]  # __getitem__ dict-compat was debt, must not exist


def test_model_provider_fetch_context_window_default_none():
    """fetch_context_window 默认返回 None（子类 override）"""

    class FakeProvider(ModelProvider):
        name = "fake"

        async def chat(self, messages, tools=None, tool_choice=None):
            return {}

        def chat_stream(self, messages, tools=None, tool_choice=None):
            yield {}

    import asyncio

    result = asyncio.run(FakeProvider().fetch_context_window())
    assert result is None


def test_model_provider_info_context_windows_default_empty():
    """ModelProviderInfo.context_windows 默认空 dict"""
    info = ModelProviderInfo(name="x", provider_class=ModelProvider, display_name="X")
    assert info.context_windows == {}


def test_model_provider_info_carries_context_windows():
    """ModelProviderInfo 可携带 context_windows"""
    info = ModelProviderInfo(
        name="x", provider_class=ModelProvider, display_name="X",
        context_windows={"my-model": 200000},
    )
    assert info.context_windows == {"my-model": 200000}
