"""Observability plugin tests."""

import pytest

from merco.observability.observer import Observer
from merco.plugins.base import PluginContext
from merco.plugins.builtin.observability.plugin import ObservabilityPlugin


@pytest.fixture
def ctx(tmp_path):
    """Construct PluginContext without an observer."""
    from unittest.mock import MagicMock

    from merco.core.agent import PromptBuilder
    from merco.core.config import MercoConfig
    from merco.hooks.registry import HookRegistry
    from merco.memory.recall import HybridRecaller
    from merco.memory.save_pipeline import MemorySavePipeline
    from merco.memory.store import MemoryStore
    from merco.tools.registry import ToolRegistry

    hooks = HookRegistry()
    tool_registry = ToolRegistry()
    prompt_builder = PromptBuilder()
    memory_store = MemoryStore(str(tmp_path / "memory"))
    config = MercoConfig()
    config.memory_path = str(tmp_path / "memory")

    return PluginContext(
        hooks=hooks,
        tool_registry=tool_registry,
        prompt_builder=prompt_builder,
        recovery_pipeline=MagicMock(),
        result_pipeline=MagicMock(),
        memory_save_pipeline=MemorySavePipeline(memory_store, hooks),
        recaller=HybridRecaller(),
        config=config,
    )


async def test_plugin_context_observer_defaults_none(ctx):
    """PluginContext can exist before observer plugin activation."""
    assert ctx.observer is None


async def test_observability_plugin_creates_observer(ctx):
    """ObservabilityPlugin creates Observer and stores it on ctx."""
    plugin = ObservabilityPlugin()
    await plugin.activate(ctx)

    assert isinstance(ctx.observer, Observer)


async def test_observability_plugin_subscribes_observer_hooks(ctx):
    """Observer created by plugin subscribes to observability events."""
    plugin = ObservabilityPlugin()
    await plugin.activate(ctx)

    assert "llm.chat" in ctx.hooks._hooks
    assert "tool.after_execute" in ctx.hooks._hooks
    assert "conversation.turn" in ctx.hooks._hooks
    assert "agent.start" in ctx.hooks._hooks


async def test_observability_plugin_metadata():
    """ObservabilityPlugin exposes stable metadata."""
    plugin = ObservabilityPlugin()

    assert plugin.name == "observability"
    assert plugin.version == "1.0.0"
    assert "observ" in plugin.description.lower()
