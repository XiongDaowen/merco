"""SubAgent plugin tests."""

import pytest

from merco.plugins.base import PluginContext
from merco.plugins.builtin.subagent.plugin import SubAgentPlugin
from merco.todo.manager import TodoManager
from merco.agents.subagent import SubAgentManager


class FakeTaskTool:
    name = "task"

    def __init__(self):
        self._todo_manager = None
        self._sub_agent_manager = None


class FakeAgent:
    def __init__(self):
        self.todo_manager = None
        self.sub_agent_manager = None


@pytest.fixture
def ctx(tmp_path):
    """Construct PluginContext with a fake agent and tool_registry containing a task tool."""
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
    tool_registry.register(FakeTaskTool())
    prompt_builder = PromptBuilder()
    memory_store = MemoryStore(str(tmp_path / "memory"))
    config = MercoConfig()
    config.memory_path = str(tmp_path / "memory")

    agent = FakeAgent()

    from merco.agents.profile import AgentProfileRegistry
    agent_profiles = AgentProfileRegistry()

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
    ctx.agent_profiles = agent_profiles
    return ctx


def test_plugin_context_todo_and_subagent_defaults_none():
    """PluginContext exposes todo_manager and sub_agent_manager with default None."""
    from merco.hooks.registry import HookRegistry
    from merco.tools.registry import ToolRegistry
    from merco.core.agent import PromptBuilder
    from merco.memory.store import MemoryStore
    from merco.memory.save_pipeline import MemorySavePipeline
    from merco.memory.recall import HybridRecaller
    from merco.core.config import MercoConfig
    from unittest.mock import MagicMock
    from tempfile import TemporaryDirectory

    with TemporaryDirectory() as tmp:
        hooks = HookRegistry()
        tool_registry = ToolRegistry()
        prompt_builder = PromptBuilder()
        memory_store = MemoryStore(str(tmp) + "/memory")
        config = MercoConfig()
        config.memory_path = str(tmp) + "/memory"

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
        assert ctx.todo_manager is None
        assert ctx.sub_agent_manager is None


async def test_subagent_plugin_creates_todo_manager(ctx):
    """SubAgentPlugin creates TodoManager and stores it on ctx."""
    plugin = SubAgentPlugin()
    await plugin.activate(ctx)

    assert isinstance(ctx.todo_manager, TodoManager)


async def test_subagent_plugin_creates_sub_agent_manager(ctx):
    """SubAgentPlugin creates SubAgentManager and stores it on ctx."""
    plugin = SubAgentPlugin()
    await plugin.activate(ctx)

    assert isinstance(ctx.sub_agent_manager, SubAgentManager)


async def test_subagent_plugin_syncs_to_agent(ctx):
    """SubAgentPlugin syncs ctx.agent.todo_manager and ctx.agent.sub_agent_manager."""
    plugin = SubAgentPlugin()
    await plugin.activate(ctx)

    assert ctx.agent.todo_manager is ctx.todo_manager
    assert ctx.agent.sub_agent_manager is ctx.sub_agent_manager


async def test_subagent_plugin_injects_into_task_tool(ctx):
    """SubAgentPlugin injects managers into the task tool."""
    plugin = SubAgentPlugin()
    await plugin.activate(ctx)

    task_tool = ctx.tool_registry.get("task")
    assert task_tool is not None
    assert task_tool._todo_manager is ctx.todo_manager
    assert task_tool._sub_agent_manager is ctx.sub_agent_manager


async def test_subagent_plugin_skips_when_no_task_tool(tmp_path):
    """SubAgentPlugin safely handles absence of task tool."""
    from merco.hooks.registry import HookRegistry
    from merco.tools.registry import ToolRegistry
    from merco.core.agent import PromptBuilder
    from merco.memory.store import MemoryStore
    from merco.memory.save_pipeline import MemorySavePipeline
    from merco.memory.recall import HybridRecaller
    from merco.core.config import MercoConfig
    from unittest.mock import MagicMock
    from merco.agents.profile import AgentProfileRegistry

    hooks = HookRegistry()
    tool_registry = ToolRegistry()  # no task tool
    prompt_builder = PromptBuilder()
    memory_store = MemoryStore(str(tmp_path / "memory"))
    config = MercoConfig()
    config.memory_path = str(tmp_path / "memory")

    agent = FakeAgent()
    agent_profiles = AgentProfileRegistry()

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
    ctx.agent_profiles = agent_profiles

    plugin = SubAgentPlugin()
    await plugin.activate(ctx)  # must not raise

    assert ctx.todo_manager is not None
    assert ctx.sub_agent_manager is not None


async def test_subagent_plugin_metadata():
    """SubAgentPlugin exposes stable metadata."""
    plugin = SubAgentPlugin()
    assert plugin.name == "subagent"
    assert plugin.version == "1.0.0"
    assert "sub" in plugin.description.lower() and "agent" in plugin.description.lower()
