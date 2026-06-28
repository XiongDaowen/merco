# Phase 3.1 ObservabilityPlugin + Agent Async Factory Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move observability toward plugin ownership by adding ObservabilityPlugin and introducing `Agent.create(...)` as the deterministic async initialization path.

**Architecture:** Add a built-in `ObservabilityPlugin` that creates `Observer(ctx.hooks)` and stores it on `PluginContext.observer`. Keep legacy `Agent(...)` compatible for existing callers, while adding `Agent.create(...)` that activates observability before `_restore_context()` and avoids the current fire-and-forget plugin race.

**Tech Stack:** Python 3.12, pytest, pytest-asyncio, existing merco PluginManager/Agent fixtures.

## Global Constraints

- TDD is mandatory: write failing test, verify failure, implement minimal code, verify pass.
- Do not begin 3.2-3.6 plugin migration in this plan.
- `ObservabilityPlugin` must create `merco.observability.observer.Observer` with `ctx.hooks`.
- `PluginContext.observer` may be `None` before ObservabilityPlugin activation.
- `Agent.create(...)` is the new authoritative async initialization path.
- Existing `Agent(...)` remains valid as a legacy compatibility path in this phase.
- Factory path must run `_restore_context()` only after ObservabilityPlugin activation.
- Factory path must synchronize `agent.observer = agent._plugin_ctx.observer` after plugin activation.
- Plugin activation must be idempotent: an already-active plugin is not activated twice.
- Do not change Observer internal counting logic or event subscriptions.

---

## File Structure

- `merco/plugins/builtin/observability/__init__.py`
  - Exports `ObservabilityPlugin`.

- `merco/plugins/builtin/observability/plugin.py`
  - Defines the built-in observability plugin.
  - One responsibility: create `Observer(ctx.hooks)` and assign `ctx.observer`.

- `merco/plugins/base.py`
  - Makes `PluginContext.observer` optional.

- `merco/plugins/manager.py`
  - Makes `activate(name)` idempotent.

- `merco/core/agent.py`
  - Adds `Agent.create(...)` async factory.
  - Adds `_defer_plugin_init` internal constructor flag.
  - Preserves legacy `Agent(...)` behavior.
  - Adds factory-path initialization order: activate observability → sync `agent.observer` → restore context → activate remaining plugins.

- `tests/plugins/test_observability_plugin.py`
  - Unit tests for ObservabilityPlugin and optional observer context.

- `tests/plugins/test_plugin_manager.py`
  - Adds idempotent activation tests.

- `tests/core/test_agent.py`
  - Adds factory-path tests.

---

### Task 1: Add ObservabilityPlugin and optional PluginContext.observer

**Files:**
- Create: `merco/plugins/builtin/observability/__init__.py`
- Create: `merco/plugins/builtin/observability/plugin.py`
- Modify: `merco/plugins/base.py`
- Create: `tests/plugins/test_observability_plugin.py`

**Interfaces:**
- Consumes: `PluginContext`, `HookRegistry`, `Observer`.
- Produces:
  - `ObservabilityPlugin.name == "observability"`
  - `ObservabilityPlugin.version == "1.0.0"`
  - `ObservabilityPlugin.activate(ctx) -> None`
  - `PluginContext(..., observer omitted)` sets `ctx.observer is None`.

- [ ] **Step 1: Write failing plugin tests**

Create `tests/plugins/test_observability_plugin.py`:

```python
"""Observability plugin tests."""

import pytest

from merco.plugins.base import PluginContext
from merco.plugins.builtin.observability.plugin import ObservabilityPlugin
from merco.observability.observer import Observer


@pytest.fixture
def ctx(tmp_path):
    """Construct PluginContext without an observer."""
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


async def test_plugin_context_observer_defaults_none(ctx):
    """PluginContext can exist before observer plugin activation."""
    assert ctx.observer is None


async def test_observability_plugin_creates_observer(ctx):
    """ObservabilityPlugin creates Observer and stores it on ctx."""
    plugin = ObservabilityPlugin()
    await plugin.activate(ctx)

    assert isinstance(ctx.observer, Observer)


async def test_observability_plugin_subscribes_observer_hooks(ctx):
    """Observer created by plugin subscribes to observability events."""
    plugin = ObservabilityPlugin()
    await plugin.activate(ctx)

    assert "llm.chat" in ctx.hooks._hooks
    assert "tool.after_execute" in ctx.hooks._hooks
    assert "conversation.turn" in ctx.hooks._hooks
    assert "agent.start" in ctx.hooks._hooks


async def test_observability_plugin_metadata():
    """ObservabilityPlugin exposes stable metadata."""
    plugin = ObservabilityPlugin()

    assert plugin.name == "observability"
    assert plugin.version == "1.0.0"
    assert "observ" in plugin.description.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
python -m pytest tests/plugins/test_observability_plugin.py -v --tb=short
```

Expected: FAIL with `ModuleNotFoundError: No module named 'merco.plugins.builtin.observability'`.

- [ ] **Step 3: Implement optional observer and ObservabilityPlugin**

In `merco/plugins/base.py`, change the `PluginContext.__init__` parameter:

```python
observer: "Observer",
```

to:

```python
observer: "Observer" = None,
```

Create `merco/plugins/builtin/observability/plugin.py`:

```python
"""Observability plugin — creates the Agent observer via plugin activation."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from merco.plugins.base import Plugin

if TYPE_CHECKING:
    from merco.plugins.base import PluginContext

logger = logging.getLogger("merco.plugins.observability")


class ObservabilityPlugin(Plugin):
    """Creates Observer and attaches it to PluginContext."""

    name = "observability"
    version = "1.0.0"
    description = "Creates the observability observer"

    async def activate(self, ctx: "PluginContext") -> None:
        from merco.observability.observer import Observer

        ctx.observer = Observer(ctx.hooks)
        logger.info("Observability plugin activated")
```

Create `merco/plugins/builtin/observability/__init__.py`:

```python
"""Observability built-in plugin."""

from .plugin import ObservabilityPlugin

__all__ = ["ObservabilityPlugin"]
```

- [ ] **Step 4: Run plugin tests to verify pass**

Run:

```bash
python -m pytest tests/plugins/test_observability_plugin.py -v --tb=short
```

Expected: 4 passed.

- [ ] **Step 5: Run existing plugin tests**

Run:

```bash
python -m pytest tests/plugins/ -v --tb=short
```

Expected: all plugin tests pass.

- [ ] **Step 6: Commit Task 1**

```bash
git add merco/plugins/base.py merco/plugins/builtin/observability/__init__.py merco/plugins/builtin/observability/plugin.py tests/plugins/test_observability_plugin.py
git commit -m "feat: add observability plugin"
```

---

### Task 2: Make PluginManager activation idempotent

**Files:**
- Modify: `merco/plugins/manager.py`
- Modify: `tests/plugins/test_plugin_manager.py`

**Interfaces:**
- Consumes: existing `PluginManager.activate(name)` and `PluginManager.activate_all()`.
- Produces:
  - `PluginManager.activate(name)` returns immediately when `name in self._active`.
  - `activate_all()` cannot re-activate already active plugins because it calls `activate(name)`.

- [ ] **Step 1: Add failing idempotency tests**

Append to `tests/plugins/test_plugin_manager.py`:

```python

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
```

- [ ] **Step 2: Run new tests to verify failure**

Run:

```bash
python -m pytest tests/plugins/test_plugin_manager.py::test_activate_is_idempotent tests/plugins/test_plugin_manager.py::test_activate_all_skips_already_active_plugins -v --tb=short
```

Expected: FAIL because `activate_count == 2`.

- [ ] **Step 3: Implement idempotent activation**

In `merco/plugins/manager.py`, at the start of `activate()` after docstring:

```python
if name in self._active:
    return
```

The method should begin:

```python
async def activate(self, name: str) -> None:
    """Activate a single plugin"""
    if name in self._active:
        return
    plugin = self._plugins.get(name)
    ...
```

- [ ] **Step 4: Run plugin manager tests**

Run:

```bash
python -m pytest tests/plugins/test_plugin_manager.py -v --tb=short
```

Expected: all plugin manager tests pass.

- [ ] **Step 5: Run full plugin suite**

Run:

```bash
python -m pytest tests/plugins/ -v --tb=short
```

Expected: all plugin tests pass.

- [ ] **Step 6: Commit Task 2**

```bash
git add merco/plugins/manager.py tests/plugins/test_plugin_manager.py
git commit -m "fix: make plugin activation idempotent"
```

---

### Task 3: Add Agent.create async factory and factory-path observability initialization

**Files:**
- Modify: `merco/core/agent.py`
- Modify: `tests/core/test_agent.py`

**Interfaces:**
- Consumes:
  - `ObservabilityPlugin` from `merco.plugins.builtin.observability.plugin`
  - Idempotent `PluginManager.activate(name)` from Task 2
- Produces:
  - `@classmethod async def Agent.create(cls, config, tool_registry=None, skill_registry=None) -> "Agent"`
  - `Agent.__init__(..., _defer_plugin_init: bool = False)`
  - `Agent._initialize_async_plugins(self) -> None`
  - Factory path activates observability before `_restore_context()`.

- [ ] **Step 1: Add failing factory tests**

Append to `tests/core/test_agent.py`:

```python

@pytest.mark.asyncio
async def test_agent_create_initializes_observer_via_plugin(monkeypatch, tmp_path):
    """Agent.create initializes observer through ObservabilityPlugin."""
    from merco.core.agent import Agent
    from merco.core.config import MercoConfig
    from merco.observability.observer import Observer
    from tests.conftest import MockLLMClient, make_test_registry

    db_path = str(tmp_path / "factory.db")
    monkeypatch.setattr("merco.core.agent.LLMClient", MockLLMClient)
    monkeypatch.setattr("merco.core.agent._get_db_path", lambda: db_path)

    cfg = MercoConfig()
    cfg.model.api_key = "test-key"
    cfg.model.model = "test-model"
    cfg.sandbox_mode = "auto"
    cfg.memory_path = str(tmp_path / "memory")

    agent = await Agent.create(config=cfg, tool_registry=make_test_registry())

    assert isinstance(agent.observer, Observer)
    assert "observability" in agent.plugin_manager.active_plugins


@pytest.mark.asyncio
async def test_agent_create_restores_observer_snapshot_after_plugin_activation(monkeypatch, tmp_path):
    """Factory path restores observer snapshot after ObservabilityPlugin creates observer."""
    from merco.core.agent import Agent
    from merco.core.config import MercoConfig
    from merco.memory.session_store import SessionStore
    from merco.core.session import Session
    from tests.conftest import MockLLMClient, make_test_registry

    db_path = str(tmp_path / "factory.db")
    store = SessionStore(db_path)
    existing = Session(store=store)
    existing.metadata["observer"] = {"acc": {"turns": 3}, "live": {}}
    store.create_session(existing.id)
    store.save_session(existing)
    store.update_current(existing.id)

    monkeypatch.setattr("merco.core.agent.LLMClient", MockLLMClient)
    monkeypatch.setattr("merco.core.agent._get_db_path", lambda: db_path)

    cfg = MercoConfig()
    cfg.model.api_key = "test-key"
    cfg.model.model = "test-model"
    cfg.sandbox_mode = "auto"
    cfg.memory_path = str(tmp_path / "memory")

    agent = await Agent.create(config=cfg, tool_registry=make_test_registry())

    report = agent.observer.report()
    assert "3 轮" in report


@pytest.mark.asyncio
async def test_agent_create_still_activates_superpower_plugin(monkeypatch, tmp_path):
    """Factory path activates remaining enabled plugins after observability."""
    from merco.core.agent import Agent
    from merco.core.config import MercoConfig
    from tests.conftest import MockLLMClient, make_test_registry

    db_path = str(tmp_path / "factory.db")
    monkeypatch.setattr("merco.core.agent.LLMClient", MockLLMClient)
    monkeypatch.setattr("merco.core.agent._get_db_path", lambda: db_path)

    cfg = MercoConfig()
    cfg.model.api_key = "test-key"
    cfg.model.model = "test-model"
    cfg.sandbox_mode = "auto"
    cfg.memory_path = str(tmp_path / "memory")

    agent = await Agent.create(config=cfg, tool_registry=make_test_registry())

    assert "superpower" in agent.plugin_manager.active_plugins
    chunk_names = [chunk.name for chunk in agent.prompt_builder._chunks]
    assert "superpower_hint" in chunk_names
```

- [ ] **Step 2: Run factory tests to verify failure**

Run:

```bash
python -m pytest tests/core/test_agent.py::test_agent_create_initializes_observer_via_plugin tests/core/test_agent.py::test_agent_create_restores_observer_snapshot_after_plugin_activation tests/core/test_agent.py::test_agent_create_still_activates_superpower_plugin -v --tb=short
```

Expected: FAIL with `AttributeError: type object 'Agent' has no attribute 'create'`.

- [ ] **Step 3: Implement Agent.create and deferred initialization path**

In `merco/core/agent.py`:

1. Change constructor signature:

```python
def __init__(self, config: MercoConfig, tool_registry=None, skill_registry=None, _defer_plugin_init: bool = False):
```

2. Keep legacy observer direct construction for `_defer_plugin_init is False`:

```python
from merco.hooks.registry import HookRegistry
self.hooks = HookRegistry()
if _defer_plugin_init:
    self.observer = None
else:
    from merco.observability.observer import Observer
    self.observer = Observer(self.hooks)
```

3. Wrap the early `_restore_context()` call:

Current code:

```python
self.session = Session.resume_or_create(self._session_store)
self._restore_context()
```

Change to:

```python
self.session = Session.resume_or_create(self._session_store)
if not _defer_plugin_init:
    self._restore_context()
```

4. Import ObservabilityPlugin with other plugin imports:

```python
from merco.plugins.builtin.observability.plugin import ObservabilityPlugin
```

5. Register ObservabilityPlugin before SuperpowerPlugin:

```python
self.plugin_manager.register(ObservabilityPlugin())
self.plugin_manager.register(SuperpowerPlugin())
```

6. Wrap the existing fire-and-forget `activate_all()` block so it only runs in legacy path:

```python
if not _defer_plugin_init:
    try:
        loop = asyncio.get_running_loop()
        asyncio.ensure_future(self.plugin_manager.activate_all())
    except RuntimeError:
        try:
            loop = asyncio.new_event_loop()
            loop.run_until_complete(self.plugin_manager.activate_all())
            loop.close()
        except Exception:
            pass
```

7. Add methods inside `class Agent` after `__init__` and before `run`:

```python
@classmethod
async def create(cls, config: MercoConfig, tool_registry=None, skill_registry=None) -> "Agent":
    """Create an Agent with deterministic async plugin initialization."""
    agent = cls(
        config=config,
        tool_registry=tool_registry,
        skill_registry=skill_registry,
        _defer_plugin_init=True,
    )
    await agent._initialize_async_plugins()
    return agent

async def _initialize_async_plugins(self) -> None:
    """Initialize plugins in deterministic order for Agent.create()."""
    await self.plugin_manager.activate("observability")
    self.observer = self._plugin_ctx.observer
    assert self.observer is not None
    self._restore_context()
    await self.plugin_manager.activate_all()
```

- [ ] **Step 4: Run factory tests**

Run:

```bash
python -m pytest tests/core/test_agent.py::test_agent_create_initializes_observer_via_plugin tests/core/test_agent.py::test_agent_create_restores_observer_snapshot_after_plugin_activation tests/core/test_agent.py::test_agent_create_still_activates_superpower_plugin -v --tb=short
```

Expected: 3 passed.

- [ ] **Step 5: Run focused Agent regressions**

Run:

```bash
python -m pytest tests/core/test_agent.py tests/integration/test_agent_loop.py tests/observability/test_observer.py -v --tb=short
```

Expected: all selected tests pass, except any known pre-existing failures already documented outside these files.

- [ ] **Step 6: Commit Task 3**

```bash
git add merco/core/agent.py tests/core/test_agent.py
git commit -m "feat: add async agent factory for plugin init"
```

---

### Task 4: Regression verification and status update

**Files:**
- Modify: `docs/project-vision/references/architecture-refactor-plan.md`

**Interfaces:**
- Consumes: Tasks 1-3 complete.
- Produces: documented 3.1 status as complete.

- [ ] **Step 1: Run focused regression suite**

Run:

```bash
python -m pytest tests/plugins/ tests/core/test_agent.py tests/integration/test_agent_loop.py tests/observability/test_observer.py -v --tb=short
```

Expected: all selected tests pass.

- [ ] **Step 2: Run full suite and record known failures**

Run:

```bash
python -m pytest tests/ -v --tb=short
```

Expected: suite may still show the known pre-existing failures from before 3.1. Confirm no new failures are caused by 3.1 files.

- [ ] **Step 3: Update architecture roadmap status**

In `docs/project-vision/references/architecture-refactor-plan.md`, change section 3.1 from:

```markdown
### 3.1 observability → ObservabilityPlugin
```

to:

```markdown
### 3.1 observability → ObservabilityPlugin ✅ 已完成
```

Add one sentence after the migration table:

```markdown
已新增 `Agent.create(...)` async factory，作为后续插件化迁移的确定性初始化路径；legacy `Agent(...)` 暂保留兼容。
```

- [ ] **Step 4: Run documentation diff check**

Run:

```bash
git diff -- docs/project-vision/references/architecture-refactor-plan.md
```

Expected: only 3.1 status and the one factory note changed.

- [ ] **Step 5: Commit Task 4**

```bash
git add docs/project-vision/references/architecture-refactor-plan.md
git commit -m "docs: mark observability plugin migration complete"
```

---

## Plan Self-Review

Spec coverage:
- ObservabilityPlugin class and plugin path: Task 1.
- PluginContext observer optional: Task 1.
- PluginManager idempotency: Task 2.
- Agent.create async factory: Task 3.
- `_defer_plugin_init` legacy/factory split: Task 3.
- Factory path activates observability before `_restore_context()`: Task 3.
- `agent.observer = agent._plugin_ctx.observer`: Task 3.
- Legacy `Agent(...)` compatibility: Task 3 focused regressions.
- Roadmap status update: Task 4.

Placeholder scan:
- No TBD/TODO/fill-in placeholders.
- Every code-changing step includes exact code.
- Every test step includes exact command and expected result.

Type consistency:
- `ObservabilityPlugin` name/version/description consistent.
- `_defer_plugin_init` spelling consistent.
- `Agent.create(...)` signature consistent.
- `_initialize_async_plugins()` name consistent.
