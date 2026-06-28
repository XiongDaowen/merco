"""Skill plugin tests."""

import pytest

from merco.plugins.base import PluginContext
from merco.plugins.builtin.skills.plugin import SkillPlugin
from merco.skills.registry import SkillRegistry


class FakeSkillTool:
    name = "skill_view"

    def __init__(self):
        self._skill_registry = None

    def set_skill_registry(self, registry):
        self._skill_registry = registry


@pytest.fixture
def ctx(tmp_path):
    """Construct PluginContext with a fake agent and tool_registry."""
    from merco.hooks.registry import HookRegistry
    from merco.tools.registry import ToolRegistry
    from merco.core.agent import PromptBuilder
    from merco.memory.store import MemoryStore
    from merco.memory.save_pipeline import MemorySavePipeline
    from merco.memory.recall import HybridRecaller
    from merco.core.config import MercoConfig
    from unittest.mock import MagicMock

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


def test_plugin_context_accepts_agent_and_skill_registry_default(ctx):
    """PluginContext can hold agent and skill_registry with default None."""
    assert ctx.agent is not None
    assert ctx.skill_registry is None


async def test_skill_plugin_creates_registry(ctx):
    """SkillPlugin creates SkillRegistry and stores it on ctx."""
    plugin = SkillPlugin()
    await plugin.activate(ctx)

    assert isinstance(ctx.skill_registry, SkillRegistry)


async def test_skill_plugin_syncs_registry_to_agent(ctx):
    """SkillPlugin syncs ctx.agent.skill_registry with the new registry."""
    plugin = SkillPlugin()
    await plugin.activate(ctx)

    assert ctx.agent.skill_registry is ctx.skill_registry


async def test_skill_plugin_injects_into_skill_view_tool(ctx):
    """SkillPlugin injects registry into the skill_view tool if present."""
    fake_tool = FakeSkillTool()
    ctx.tool_registry.register(fake_tool)

    plugin = SkillPlugin()
    await plugin.activate(ctx)

    assert fake_tool._skill_registry is ctx.skill_registry


async def test_skill_plugin_skips_when_tool_view_missing(ctx):
    """SkillPlugin safely handles absence of skill_view tool."""
    plugin = SkillPlugin()
    await plugin.activate(ctx)

    assert ctx.skill_registry is not None


async def test_skill_plugin_metadata():
    """SkillPlugin exposes stable metadata."""
    plugin = SkillPlugin()
    assert plugin.name == "skills"
    assert plugin.version == "1.0.0"
    assert "skill" in plugin.description.lower()
