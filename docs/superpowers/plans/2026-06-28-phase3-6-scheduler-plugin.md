# Phase 3.6 SchedulerPlugin Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move CronScheduler creation into a built-in SchedulerPlugin so the scheduler becomes a plugin-owned subsystem.

**Architecture:** Add a SchedulerPlugin whose activate(ctx) creates CronScheduler and stores it on ctx.scheduler. Extend PluginContext with scheduler field. Wire the plugin into Agent.create(...) activation order. Do not auto-start the scheduler.

**Tech Stack:** Python 3.12, pytest, pytest-asyncio, existing merco Plugin/Agent fixtures.

## Global Constraints

- TDD is mandatory.
- Do not auto-start CronScheduler.start() in the plugin.
- PluginContext.scheduler defaults to None.
- Plugin is activated last among builtins before activate_all().

---

### Task 1: SchedulerPlugin + unit tests + wire Agent + roadmap

**Files:**
- Create: `merco/plugins/builtin/scheduler/__init__.py`
- Create: `merco/plugins/builtin/scheduler/plugin.py`
- Create: `tests/plugins/test_scheduler_plugin.py`
- Modify: `merco/plugins/base.py`
- Modify: `merco/core/agent.py`
- Modify: `docs/project-vision/references/architecture-refactor-plan.md`

**Interfaces:**
- Consumes: PluginContext, CronScheduler.
- Produces:
  - `SchedulerPlugin.name == "scheduler"`, `version == "1.0.0"`
  - `SchedulerPlugin.activate(ctx)` creates CronScheduler, sets ctx.scheduler.
  - `PluginContext(..., scheduler=None)` is valid.

- [ ] **Step 1: Write failing tests**

Create `tests/plugins/test_scheduler_plugin.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify failure**

```bash
python -m pytest tests/plugins/test_scheduler_plugin.py -v --tb=short
```

Expected: FAIL with ModuleNotFoundError or TypeError.

- [ ] **Step 3: Implement**

Create `merco/plugins/builtin/scheduler/plugin.py`:

```python
"""Scheduler plugin — creates CronScheduler."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from merco.plugins.base import Plugin

if TYPE_CHECKING:
    from merco.plugins.base import PluginContext

logger = logging.getLogger("merco.plugins.scheduler")


class SchedulerPlugin(Plugin):
    """Creates CronScheduler and attaches it to PluginContext."""

    name = "scheduler"
    version = "1.0.0"
    description = "Creates the cron scheduler"

    async def activate(self, ctx: "PluginContext") -> None:
        from merco.scheduler.cron import CronScheduler

        ctx.scheduler = CronScheduler()
        logger.info("Scheduler plugin activated")
```

Create `merco/plugins/builtin/scheduler/__init__.py`:

```python
"""Scheduler built-in plugin."""

from .plugin import SchedulerPlugin

__all__ = ["SchedulerPlugin"]
```

In `merco/plugins/base.py`: add `CronScheduler` to TYPE_CHECKING imports; add `scheduler: "CronScheduler" = None` to PluginContext.__init__ params; set `self.scheduler = scheduler`.

In `merco/core/agent.py`:
1. Add import: `from merco.plugins.builtin.scheduler.plugin import SchedulerPlugin`
2. Register `SchedulerPlugin()` after `WebPlugin()`, before `SuperpowerPlugin()`
3. In `_initialize_async_plugins()`, add `await self.plugin_manager.activate("scheduler")` after `web`, before `activate_all()`

In `docs/project-vision/references/architecture-refactor-plan.md`, mark 3.6 as ✅ completed.

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/plugins/test_scheduler_plugin.py -v --tb=short
```

Expected: 4 passed.

- [ ] **Step 5: Run plugin suite + focused regressions**

```bash
python -m pytest tests/plugins/ tests/core/test_agent.py tests/cli/test_cli_help.py tests/integration/test_agent_loop.py -v --tb=short
```

Expected: all pass.

- [ ] **Step 6: Run full suite**

```bash
python -m pytest tests/ -q --tb=line
```

Expected: same 9 pre-existing failures; no new failures.

- [ ] **Step 7: Commit**

```bash
git add merco/plugins/builtin/scheduler/__init__.py merco/plugins/builtin/scheduler/plugin.py merco/plugins/base.py merco/core/agent.py tests/plugins/test_scheduler_plugin.py docs/project-vision/references/architecture-refactor-plan.md
git commit -m "feat: add scheduler plugin"
```
