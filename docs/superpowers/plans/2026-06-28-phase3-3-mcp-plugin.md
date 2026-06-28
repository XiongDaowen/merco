# Phase 3.3 MCPPlugin Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move `MCPServerManager` creation out of `Agent.__init__` into a built-in `MCPPlugin` so that the manager becomes a first-class plugin-owned subsystem and `Agent.create(...)` factory path can initialize it deterministically.

**Architecture:** Add a built-in `MCPPlugin` whose `activate(ctx)` only constructs the manager and wires it to `ctx.mcp_manager` and `ctx.agent.mcp_manager`. The plugin does not perform any network or stdio I/O; loading MCP servers remains an explicit caller step. The existing `CloseMCPConnections` cleanup path keeps reading `agent.mcp_manager` (now optionally `None`) and `shutdown()` is awaited safely.

**Tech Stack:** Python 3.12, pytest, pytest-asyncio, existing merco Plugin/Agent fixtures.

## Global Constraints

- TDD is mandatory: write failing test, verify failure, implement minimal code, verify pass.
- Do not begin 3.4-3.6 plugin migration in this plan.
- `Agent.__init__` must NOT construct `MCPServerManager`; `self.mcp_manager = None`.
- `MCPPlugin.activate(ctx)` must NOT call `load_config`, `connect`, or any other I/O method on the manager.
- `MCPPlugin.activate(ctx)` must set `ctx.mcp_manager` and `ctx.agent.mcp_manager` to the same instance.
- `PluginContext.mcp_manager` is optional with default `None`.
- `_initialize_async_plugins()` activates `mcp` between `skills` and `activate_all`.
- `CloseMCPConnections` must remain unchanged and continue to read `agent.mcp_manager`.
- The legacy `test_agent_has_mcp_manager` test must be rewritten to cover the factory path (legacy `Agent(...)` path no longer populates `mcp_manager`).

---

## File Structure

- `merco/plugins/builtin/mcp/__init__.py`
  - Exports `MCPPlugin`.

- `merco/plugins/builtin/mcp/plugin.py`
  - Defines `MCPPlugin`. Single responsibility: create `MCPServerManager` and assign to ctx.

- `merco/plugins/base.py`
  - Adds `mcp_manager: MCPServerManager | None = None` to `PluginContext.__init__`.

- `merco/core/agent.py`
  - Removes direct `MCPServerManager` creation from `__init__`.
  - Sets `self.mcp_manager = None` in `__init__`.
  - Registers `MCPPlugin` alongside `ObservabilityPlugin`/`SkillPlugin`.
  - Activates `mcp` in `_initialize_async_plugins()`.

- `tests/plugins/test_mcp_plugin.py`
  - Unit tests for MCPPlugin activation behavior.

- `tests/core/test_agent.py`
  - Convert `test_agent_has_mcp_manager` to factory path coverage.

- `tests/integration/test_interrupt_flow.py`
  - Update `mcp_manager = MagicMock()` lines to be `AsyncMock`-compatible (since `shutdown()` is async).

---

### Task 1: Add MCPPlugin and extend PluginContext

**Files:**
- Create: `tests/plugins/test_mcp_plugin.py`
- Create: `merco/plugins/builtin/mcp/__init__.py`
- Create: `merco/plugins/builtin/mcp/plugin.py`
- Modify: `merco/plugins/base.py`

**Interfaces:**
- Consumes: `PluginContext`, `MCPServerManager`.
- Produces:
  - `MCPPlugin.name == "mcp"`
  - `MCPPlugin.version == "1.0.0"`
  - `MCPPlugin.activate(ctx) -> None`
  - `PluginContext(..., mcp_manager=None)` is valid.

- [ ] **Step 1: Write failing plugin tests**

Create `tests/plugins/test_mcp_plugin.py`:

```python
"""MCP plugin tests."""

import pytest

from merco.plugins.base import PluginContext
from merco.plugins.builtin.mcp.plugin import MCPPlugin
from merco.mcp.manager import MCPServerManager


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

    # MCPServerManager has load_config, connect, shutdown, status, reload
    # None of these should be invoked by activation.
    assert ctx.mcp_manager._servers == {}


async def test_mcp_plugin_metadata():
    """MCPPlugin exposes stable metadata."""
    plugin = MCPPlugin()
    assert plugin.name == "mcp"
    assert plugin.version == "1.0.0"
    assert "mcp" in plugin.description.lower()
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
python -m pytest tests/plugins/test_mcp_plugin.py -v --tb=short
```

Expected: FAIL with `ModuleNotFoundError` or `TypeError` because `PluginContext` doesn't accept `mcp_manager`.

- [ ] **Step 3: Implement PluginContext extension and MCPPlugin**

In `merco/plugins/base.py`:

1. Add `MCPServerManager` to TYPE_CHECKING imports:

```python
from merco.mcp.manager import MCPServerManager
```

2. Add `mcp_manager: "MCPServerManager" = None` to `PluginContext.__init__` parameters (at the end of the signature).

3. Add `self.mcp_manager = mcp_manager` inside `__init__`.

Create `merco/plugins/builtin/mcp/plugin.py`:

```python
"""MCP plugin — creates the MCP server manager."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from merco.plugins.base import Plugin

if TYPE_CHECKING:
    from merco.plugins.base import PluginContext

logger = logging.getLogger("merco.plugins.mcp")


class MCPPlugin(Plugin):
    """Creates MCPServerManager and attaches it to PluginContext.

    This plugin performs NO network or stdio I/O. Loading MCP servers
    remains an explicit caller step (e.g. via `mcp_manager.load_config(...)`).
    """

    name = "mcp"
    version = "1.0.0"
    description = "Creates the MCP server manager"

    async def activate(self, ctx: "PluginContext") -> None:
        from merco.mcp.manager import MCPServerManager

        manager = MCPServerManager(
            tool_registry=ctx.tool_registry,
            hooks=ctx.hooks,
        )
        ctx.mcp_manager = manager
        if ctx.agent is not None:
            ctx.agent.mcp_manager = manager

        logger.info("MCP plugin activated")
```

Create `merco/plugins/builtin/mcp/__init__.py`:

```python
"""MCP built-in plugin."""

from .plugin import MCPPlugin

__all__ = ["MCPPlugin"]
```

- [ ] **Step 4: Run plugin tests**

Run:

```bash
python -m pytest tests/plugins/test_mcp_plugin.py -v --tb=short
```

Expected: 5 passed.

- [ ] **Step 5: Run existing plugin tests**

Run:

```bash
python -m pytest tests/plugins/ -v --tb=short
```

Expected: all pass.

- [ ] **Step 6: Commit Task 1**

```bash
git add merco/plugins/base.py merco/plugins/builtin/mcp/__init__.py merco/plugins/builtin/mcp/plugin.py tests/plugins/test_mcp_plugin.py
git commit -m "feat: add mcp plugin and ctx.mcp_manager"
```

---

### Task 2: Wire MCPPlugin into Agent factory path

**Files:**
- Modify: `merco/core/agent.py`
- Modify: `tests/core/test_agent.py`

**Interfaces:**
- Consumes: `MCPPlugin` from Task 1.
- Produces:
  - `Agent.__init__` no longer constructs `MCPServerManager`; sets `self.mcp_manager = None`.
  - `_initialize_async_plugins()` activates `mcp` between `skills` and `activate_all`.
  - `MCPPlugin` registered alongside other builtins.

- [ ] **Step 1: Convert legacy mcp_manager test to factory path**

In `tests/core/test_agent.py`, replace the existing function:

```python
def test_agent_has_mcp_manager(test_agent):
    assert hasattr(test_agent, 'mcp_manager')
    from merco.mcp.manager import MCPServerManager
    assert isinstance(test_agent.mcp_manager, MCPServerManager)
```

with:

```python

@pytest.mark.asyncio
async def test_agent_create_initializes_mcp_manager(monkeypatch, tmp_path):
    """Agent.create initializes MCPPlugin-created MCPServerManager."""
    from merco.core.agent import Agent
    from merco.core.config import MercoConfig
    from merco.mcp.manager import MCPServerManager
    from tests.conftest import MockLLMClient, make_test_registry

    db_path = str(tmp_path / "factory_mcp.db")
    monkeypatch.setattr("merco.core.agent.LLMClient", MockLLMClient)
    monkeypatch.setattr("merco.core.agent._get_db_path", lambda: db_path)

    cfg = MercoConfig()
    cfg.model.api_key = "test-key"
    cfg.model.model = "test-model"
    cfg.sandbox_mode = "auto"
    cfg.memory_path = str(tmp_path / "memory")

    agent = await Agent.create(config=cfg, tool_registry=make_test_registry())

    assert isinstance(agent.mcp_manager, MCPServerManager)
    assert "mcp" in agent.plugin_manager.active_plugins
```

- [ ] **Step 2: Run converted test to verify it fails**

Run:

```bash
python -m pytest tests/core/test_agent.py::test_agent_create_initializes_mcp_manager -v --tb=short
```

Expected: FAIL because `Agent.create(...)` does not activate `mcp` plugin yet.

- [ ] **Step 3: Modify Agent**

In `merco/core/agent.py`:

1. Replace the block:

```python
        # ── MCP 客户端 ──
        from merco.mcp.manager import MCPServerManager
        self.mcp_manager = MCPServerManager(
            tool_registry=self.tool_registry,
            hooks=self.hooks,
        )
```

with:

```python
        # ── MCP 客户端（由 MCPPlugin 激活时创建；legacy 路径下保持 None）──
        self.mcp_manager = None
```

2. Add `MCPPlugin` import near the other plugin imports:

```python
from merco.plugins.builtin.mcp.plugin import MCPPlugin
```

3. Register `MCPPlugin` between `SkillPlugin` and `SuperpowerPlugin`:

```python
self.plugin_manager.register(ObservabilityPlugin())
self.plugin_manager.register(SkillPlugin())
self.plugin_manager.register(MCPPlugin())
self.plugin_manager.register(SuperpowerPlugin())
```

4. Update `_initialize_async_plugins()` to activate `mcp`:

```python
async def _initialize_async_plugins(self) -> None:
    """Initialize plugins in deterministic order for Agent.create()."""
    await self.plugin_manager.activate("observability")
    self.observer = self._plugin_ctx.observer
    assert self.observer is not None
    self._restore_context()
    await self.plugin_manager.activate("skills")
    await self.plugin_manager.activate("mcp")
    await self.plugin_manager.activate_all()
```

- [ ] **Step 4: Run factory test**

Run:

```bash
python -m pytest tests/core/test_agent.py::test_agent_create_initializes_mcp_manager -v --tb=short
```

Expected: PASS.

- [ ] **Step 5: Run focused regressions**

Run:

```bash
python -m pytest tests/core/test_agent.py tests/integration/test_agent_loop.py tests/plugins/ tests/mcp/ tests/observability/test_observer.py -v --tb=short
```

Expected: all selected tests pass.

- [ ] **Step 6: Commit Task 2**

```bash
git add merco/core/agent.py tests/core/test_agent.py
git commit -m "refactor: wire mcp plugin into agent factory"
```

---

### Task 3: Verify and adapt MCP-related interrupt tests

**Files:**
- Modify: `tests/integration/test_interrupt_flow.py`
- Modify: `tests/core/test_interrupt.py`

**Interfaces:**
- Consumes: `Agent.mcp_manager` is now None by default for legacy path, or `MCPServerManager` for factory path.
- Produces: interrupt tests still pass because `CloseMCPConnections` already guards `if ctx.agent.mcp_manager:`.

- [ ] **Step 1: Run interrupt tests to identify any failures**

Run:

```bash
python -m pytest tests/integration/test_interrupt_flow.py tests/core/test_interrupt.py -v --tb=short
```

Expected: tests that explicitly set `agent.mcp_manager = MagicMock()` and `agent.mcp_manager.shutdown = AsyncMock()` should still pass because they manually inject the manager. The check `if ctx.agent.mcp_manager:` in `CloseMCPConnections` handles both populated and None cases.

- [ ] **Step 2: If any test failed because mcp_manager is None, adapt to set it explicitly**

If Step 1 surfaces a test that constructs `test_agent` via legacy path and then asserts something on `agent.mcp_manager`, update that test to either:

- Use `await Agent.create(...)` instead of `test_agent` fixture, or
- Set `agent.mcp_manager = MCPServerManager(...)` explicitly if the test only needs the manager present.

Document any such changes in the commit message.

- [ ] **Step 3: Re-run interrupt tests**

Run:

```bash
python -m pytest tests/integration/test_interrupt_flow.py tests/core/test_interrupt.py -v --tb=short
```

Expected: all pass.

- [ ] **Step 4: Commit Task 3**

```bash
git add tests/integration/test_interrupt_flow.py tests/core/test_interrupt.py
git commit -m "test: keep interrupt tests green after mcp plugin migration"
```

---

### Task 4: Regression verification and roadmap update

**Files:**
- Modify: `docs/project-vision/references/architecture-refactor-plan.md`

**Interfaces:**
- Consumes: Tasks 1-3 complete.
- Produces: documented 3.3 status as complete.

- [ ] **Step 1: Run focused regression suite**

Run:

```bash
python -m pytest tests/plugins/ tests/core/test_agent.py tests/mcp/ tests/integration/test_agent_loop.py tests/integration/test_interrupt_flow.py tests/core/test_interrupt.py tests/observability/test_observer.py -v --tb=short
```

Expected: all selected tests pass.

- [ ] **Step 2: Run full suite and confirm no new failures**

Run:

```bash
python -m pytest tests/ -q --tb=line
```

Expected: same 9 pre-existing failures from before 3.3; no new failures introduced by MCPPlugin migration.

- [ ] **Step 3: Update architecture roadmap status**

In `docs/project-vision/references/architecture-refactor-plan.md`, change section 3.3 from:

```markdown
### 3.3 mcp → MCPPlugin
```

to:

```markdown
### 3.3 mcp → MCPPlugin ✅ 已完成
```

Add one sentence after the migration table:

```markdown
`MCPPlugin` 只负责创建 `MCPServerManager`，激活阶段不触发任何网络/stdio I/O；加载 MCP 服务器仍由调用方显式触发。
```

- [ ] **Step 4: Verify docs diff**

Run:

```bash
git diff -- docs/project-vision/references/architecture-refactor-plan.md
```

Expected: only 3.3 status and the MCPPlugin note changed.

- [ ] **Step 5: Commit Task 4**

```bash
git add docs/project-vision/references/architecture-refactor-plan.md
git commit -m "docs: mark mcp plugin migration complete"
```

---

## Plan Self-Review

Spec coverage:
- MCPPlugin class and file path: Task 1.
- `PluginContext.mcp_manager` extension: Task 1.
- `Agent.__init__` no longer creates MCPServerManager: Task 2.
- `_initialize_async_plugins` activates `mcp`: Task 2.
- `MCPPlugin` registered: Task 2.
- `CloseMCPConnections` compatibility (no code change needed; tested via regression): Task 3.
- `test_agent_has_mcp_manager` legacy test rewritten to factory path: Task 2.
- Roadmap status update: Task 4.

Placeholder scan:
- No TBD/TODO/fill-in placeholders.
- Every code-changing step has exact code.
- Every test step has exact command and expected result.

Type consistency:
- `MCPPlugin` name/version/description consistent.
- `PluginContext` field name `mcp_manager` consistent across tasks.
- `_initialize_async_plugins` activation order consistent: observability → restore → skills → mcp → activate_all.
- Task 3 reads as "verify-and-adapt" because interrupt tests already use `if ctx.agent.mcp_manager:` guards; only documented adaptation is needed if tests surface new failures.