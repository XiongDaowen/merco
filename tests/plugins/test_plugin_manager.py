"""PluginManager unit tests"""
import pytest

from merco.plugins.base import Plugin, PluginContext
from merco.plugins.manager import PluginManager


class FakePlugin(Plugin):
    name = "fake"
    version = "1.0.0"
    description = "test plugin"

    def __init__(self):
        self.activated = False
        self.deactivated = False

    async def activate(self, ctx):
        self.activated = True

    async def deactivate(self):
        self.deactivated = True


class FailingPlugin(Plugin):
    name = "failing"
    version = "1.0.0"
    description = "plugin that fails on activate"

    async def activate(self, ctx):
        raise RuntimeError("boom")

    async def deactivate(self):
        pass


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


@pytest.fixture
def manager(ctx):
    return PluginManager(ctx)


async def test_activate_single_plugin(manager, ctx):
    """Activate a single plugin"""
    plugin = FakePlugin()
    manager._plugins["fake"] = plugin
    await manager.activate("fake")
    assert plugin.activated is True
    assert "fake" in manager._active


async def test_deactivate_plugin(manager, ctx):
    """Deactivate a plugin"""
    plugin = FakePlugin()
    manager._plugins["fake"] = plugin
    await manager.activate("fake")
    await manager.deactivate("fake")
    assert plugin.deactivated is True
    assert "fake" not in manager._active


async def test_activate_emits_event(manager, ctx):
    """Activating a plugin emits plugin.activated event"""
    events = []
    async def on_activated(plugin_name, **kwargs):
        events.append(plugin_name)
    ctx.hooks.on("plugin.activated", on_activated)

    manager._plugins["fake"] = FakePlugin()
    await manager.activate("fake")
    assert "fake" in events


async def test_activate_all_enabled(manager, ctx):
    """activate_all only activates enabled plugins"""
    ctx.config.plugins = {
        "fake": {"enabled": True},
        "disabled": {"enabled": False},
    }
    plugin = FakePlugin()
    manager._plugins["fake"] = plugin
    manager._plugins["disabled"] = FakePlugin()

    await manager.activate_all()
    assert plugin.activated is True
    assert manager._plugins["disabled"].activated is False


async def test_activate_failure_isolated(manager, ctx):
    """Plugin activation failure does not affect other plugins"""
    events = []
    async def on_error(plugin_name, **kwargs):
        events.append(plugin_name)
    ctx.hooks.on("plugin.error", on_error)

    manager._plugins["failing"] = FailingPlugin()
    manager._plugins["fake"] = FakePlugin()
    await manager.activate_all()
    assert "failing" in events
    assert manager._plugins["fake"].activated is True


class CountingPlugin(Plugin):
    name = "counting"
    version = "1.0.0"
    description = "counts activations"

    def __init__(self):
        self.activate_count = 0

    async def activate(self, ctx):
        self.activate_count += 1


async def test_activate_is_idempotent(manager):
    """Activating an already-active plugin does not call activate twice."""
    plugin = CountingPlugin()
    manager.register(plugin)

    await manager.activate("counting")
    await manager.activate("counting")

    assert plugin.activate_count == 1
    assert manager.active_plugins.count("counting") == 1


async def test_activate_all_skips_already_active_plugins(manager):
    """activate_all does not re-activate plugins already in _active."""
    plugin = CountingPlugin()
    manager.register(plugin)

    await manager.activate("counting")
    await manager.activate_all()

    assert plugin.activate_count == 1
