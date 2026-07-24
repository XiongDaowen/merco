"""Superpower plugin unit tests"""
import pytest

from merco.plugins.base import PluginContext
from merco.plugins.builtin.superpower.plugin import SuperpowerPlugin


@pytest.fixture
def ctx(tmp_path):
    """Construct PluginContext"""
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
        observer=MagicMock(),
    )


async def test_superpower_subscribes_events(ctx):
    """Superpower plugin subscribes to agent.start and tool.error events"""
    plugin = SuperpowerPlugin()
    await plugin.activate(ctx)
    assert "agent.start" in ctx.hooks._hooks
    assert "tool.error" in ctx.hooks._hooks


async def test_superpower_adds_prompt_chunk(ctx):
    """Superpower plugin injects a prompt chunk"""
    plugin = SuperpowerPlugin()
    await plugin.activate(ctx)
    chunk_names = [c.name for c in ctx.prompt_builder._chunks]
    assert any("superpower" in name.lower() for name in chunk_names)


async def test_superpower_has_correct_metadata(ctx):
    """Superpower plugin has correct name and version"""
    plugin = SuperpowerPlugin()
    assert plugin.name == "superpower"
    assert plugin.version == "1.0.0"


async def test_superpower_hint_chunk_build(ctx):
    """SuperpowerHintChunk produces valid content"""
    from merco.plugins.builtin.superpower.plugin import SuperpowerHintChunk

    chunk = SuperpowerHintChunk()
    assert chunk.name == "superpower_hint"
    assert chunk.enabled(None) is True
    text = chunk.build(None)
    assert "superpower" in text.lower()


async def test_superpower_deactivate_noop(ctx):
    """Superpower plugin deactivate does not raise"""
    plugin = SuperpowerPlugin()
    await plugin.activate(ctx)
    await plugin.deactivate()
