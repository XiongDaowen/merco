"""Scheduler plugin tests."""

import pytest

from merco.plugins.base import PluginContext
from merco.plugins.builtin.scheduler.plugin import SchedulerPlugin
from merco.scheduler.cron import CronScheduler


@pytest.fixture
def ctx(tmp_path):
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


def test_plugin_context_scheduler_defaults_none(ctx):
    assert ctx.scheduler is None


async def test_scheduler_plugin_creates_scheduler(ctx):
    plugin = SchedulerPlugin()
    await plugin.activate(ctx)
    assert isinstance(ctx.scheduler, CronScheduler)


async def test_scheduler_plugin_does_not_auto_start(ctx):
    plugin = SchedulerPlugin()
    await plugin.activate(ctx)
    assert ctx.scheduler._running is False


async def test_scheduler_plugin_metadata():
    plugin = SchedulerPlugin()
    assert plugin.name == "scheduler"
    assert plugin.version == "1.0.0"
