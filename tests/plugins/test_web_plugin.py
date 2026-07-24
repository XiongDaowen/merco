"""Web plugin tests."""

import pytest

from merco.plugins.base import PluginContext
from merco.plugins.builtin.web.plugin import WebPlugin


@pytest.fixture
def ctx(tmp_path):
    """Construct PluginContext with tool_registry."""
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


async def test_web_plugin_registers_web_fetch(ctx):
    """WebPlugin registers WebFetch tool."""
    plugin = WebPlugin()
    await plugin.activate(ctx)

    tool = ctx.tool_registry.get("web_fetch")
    assert tool is not None


async def test_web_plugin_registers_web_search(ctx):
    """WebPlugin registers WebSearch tool."""
    plugin = WebPlugin()
    await plugin.activate(ctx)

    tool = ctx.tool_registry.get("web_search")
    assert tool is not None


async def test_web_plugin_metadata():
    """WebPlugin exposes stable metadata."""
    plugin = WebPlugin()
    assert plugin.name == "web"
    assert plugin.version == "1.0.0"
    assert "web" in plugin.description.lower()
