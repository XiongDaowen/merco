# Phase 3.5 WebPlugin Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move WebFetch/WebSearch registration from import-time side effect in `merco/tools/web_tools.py` into a built-in WebPlugin.

**Architecture:** Add a built-in `WebPlugin` whose `activate(ctx)` registers `WebFetch()` and `WebSearch()` via `ctx.register_tool()`. Remove the two-line auto-registration block from `web_tools.py`. Wire the plugin into `Agent.create(...)` activation order.

**Tech Stack:** Python 3.12, pytest, pytest-asyncio, existing merco Plugin/Agent fixtures.

## Global Constraints

- TDD is mandatory: write failing test, verify failure, implement minimal code, verify pass.
- Do not begin 3.6 (SchedulerPlugin) in this plan.
- WebPlugin.activate(ctx) must register `WebFetch()` and `WebSearch()` via `ctx.register_tool()`.
- The import-time side effect in `merco/tools/web_tools.py` (bottom two lines) must be removed.
- WebPlugin is the last builtin activated before `activate_all()`.

---

### Task 1: WebPlugin + unit tests + remove import-time auto-registration

**Files:**
- Create: `merco/plugins/builtin/web/__init__.py`
- Create: `merco/plugins/builtin/web/plugin.py`
- Create: `tests/plugins/test_web_plugin.py`
- Modify: `merco/tools/web_tools.py`
- Modify: `merco/core/agent.py`

**Interfaces:**
- Consumes: `PluginContext` (with `tool_registry`).
- Produces:
  - `WebPlugin.name == "web"`, `version == "1.0.0"`
  - `WebPlugin.activate(ctx)` registers web_fetch and web_search tools.
  - `merco/tools/web_tools.py` no longer auto-registers at import time.
  - Agent registers and activates WebPlugin.

- [ ] **Step 1: Write failing WebPlugin tests**

Create `tests/plugins/test_web_plugin.py`:

```python
"""Web plugin tests."""

import pytest

from merco.plugins.base import PluginContext
from merco.plugins.builtin.web.plugin import WebPlugin


@pytest.fixture
def ctx(tmp_path):
    """Construct PluginContext with tool_registry."""
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
```

- [ ] **Step 2: Run tests to verify failure**

```bash
python -m pytest tests/plugins/test_web_plugin.py -v --tb=short
```

Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Create WebPlugin, remove auto-registration, wire into Agent**

Create `merco/plugins/builtin/web/plugin.py`:

```python
"""Web plugin — registers web tools."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from merco.plugins.base import Plugin

if TYPE_CHECKING:
    from merco.plugins.base import PluginContext

logger = logging.getLogger("merco.plugins.web")


class WebPlugin(Plugin):
    """Registers WebFetch and WebSearch tools."""

    name = "web"
    version = "1.0.0"
    description = "Registers web tools (fetch and search)"

    async def activate(self, ctx: "PluginContext") -> None:
        from merco.tools.web_tools import WebFetch, WebSearch

        ctx.register_tool(WebFetch())
        ctx.register_tool(WebSearch())

        logger.info("Web plugin activated")
```

Create `merco/plugins/builtin/web/__init__.py`:

```python
"""Web built-in plugin."""

from .plugin import WebPlugin

__all__ = ["WebPlugin"]
```

In `merco/tools/web_tools.py`, delete the final two lines:

```python
from .registry import tool_registry  # noqa: E402 — 模块末尾自注册
tool_registry.register(WebFetch())
tool_registry.register(WebSearch())
```

In `merco/core/agent.py`:

1. Add import: `from merco.plugins.builtin.web.plugin import WebPlugin`
2. Register: `self.plugin_manager.register(WebPlugin())` after SubAgentPlugin, before SuperpowerPlugin
3. In `_initialize_async_plugins()`, add `await self.plugin_manager.activate("web")` after `subagent`, before `activate_all()`

- [ ] **Step 4: Run WebPlugin tests**

```bash
python -m pytest tests/plugins/test_web_plugin.py -v --tb=short
```

Expected: 3 passed.

- [ ] **Step 5: Run full plugin suite**

```bash
python -m pytest tests/plugins/ -v --tb=short
```

Expected: all pass.

- [ ] **Step 6: Run focused regressions**

```bash
python -m pytest tests/tools/ tests/integration/test_agent_loop.py tests/cli/test_cli_help.py tests/core/test_agent.py -v --tb=short
```

Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add merco/plugins/builtin/web/__init__.py merco/plugins/builtin/web/plugin.py merco/tools/web_tools.py merco/core/agent.py tests/plugins/test_web_plugin.py
git commit -m "feat: add web plugin and remove import-time tool registration"
```

---

### Task 2: Regression verification and roadmap update

**Files:**
- Modify: `docs/project-vision/references/architecture-refactor-plan.md`

- [ ] **Step 1: Run full suite**

```bash
python -m pytest tests/ -q --tb=line
```

Expected: same 9 pre-existing failures; no new failures.

- [ ] **Step 2: Update roadmap**

Mark 3.5 as ✅ completed. One sentence: "`WebPlugin` 通过插件注册 WebFetch/WebSearch，移除模块 import 副作用。"

- [ ] **Step 3: Commit**

```bash
git add docs/project-vision/references/architecture-refactor-plan.md
git commit -m "docs: mark web plugin migration complete"
```
