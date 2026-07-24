"""MCP plugin tests."""

import pytest

from merco.mcp.manager import MCPServerManager
from merco.plugins.base import PluginContext
from merco.plugins.builtin.mcp.plugin import MCPPlugin


@pytest.fixture
def ctx(tmp_path):
    """Construct PluginContext with a fake agent and tool_registry."""
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

    class FakeAgent:
        pass

    agent = FakeAgent()
    ctx = PluginContext(
        hooks=hooks,
        tool_registry=tool_registry,
        prompt_builder=prompt_builder,
        recovery_pipeline=MagicMock(),
        result_pipeline=MagicMock(),
        memory_save_pipeline=MemorySavePipeline(memory_store, hooks),
        recaller=HybridRecaller(),
        config=config,
    )
    ctx.agent = agent
    return ctx


def test_plugin_context_mcp_manager_defaults_none(ctx):
    """PluginContext exposes mcp_manager with default None."""
    assert ctx.mcp_manager is None


async def test_mcp_plugin_creates_manager(ctx):
    """MCPPlugin creates MCPServerManager and stores it on ctx."""
    plugin = MCPPlugin()
    await plugin.activate(ctx)

    assert isinstance(ctx.mcp_manager, MCPServerManager)


async def test_mcp_plugin_syncs_manager_to_agent(ctx):
    """MCPPlugin syncs ctx.agent.mcp_manager with the new manager."""
    plugin = MCPPlugin()
    await plugin.activate(ctx)

    assert ctx.agent.mcp_manager is ctx.mcp_manager


async def test_mcp_plugin_does_not_perform_io(ctx):
    """MCPPlugin.activate must NOT call load_config or connect."""
    plugin = MCPPlugin()
    await plugin.activate(ctx)

    assert ctx.mcp_manager._servers == {}


async def test_mcp_plugin_metadata():
    """MCPPlugin exposes stable metadata."""
    plugin = MCPPlugin()
    assert plugin.name == "mcp"
    assert plugin.version == "1.0.0"
    assert "mcp" in plugin.description.lower()
