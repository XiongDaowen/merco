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
