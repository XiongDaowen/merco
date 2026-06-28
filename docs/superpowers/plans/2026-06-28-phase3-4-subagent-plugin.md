# Phase 3.4 SubAgentPlugin + CLI e2e Smoke Test Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move `TodoManager`, `SubAgentManager`, and `TaskTool` injection out of `Agent.__init__` into a built-in `SubAgentPlugin`, and add a CLI smoke test that catches import-time regressions in `merco run --help`.

**Architecture:** Add a built-in `SubAgentPlugin` whose `activate(ctx)` creates `TodoManager` and `SubAgentManager`, syncs them onto `ctx.agent`, and injects them into the `task` tool if present. Wire the plugin into `Agent.create(...)` activation. Add a new `tests/cli/test_cli_help.py` that uses `typer.testing.CliRunner` to invoke `merco run --help`, `merco --help`, and `merco init --help` — these catch the class of bugs the existing mock-heavy tests missed (e.g., a deleted constructor parameter still passed by the CLI).

**Tech Stack:** Python 3.12, pytest, pytest-asyncio, typer + typer.testing.CliRunner, existing merco Plugin/Agent fixtures.

## Global Constraints

- TDD is mandatory: write failing test, verify failure, implement minimal code, verify pass.
- Do not begin 3.5-3.6 plugin migration in this plan.
- `SubAgentPlugin.activate(ctx)` must create `TodoManager` and `SubAgentManager`; no filesystem I/O beyond `TodoManager`'s constructor (which already creates its SQLite directory).
- `SubAgentPlugin.activate(ctx)` must set `ctx.todo_manager`, `ctx.sub_agent_manager`, `ctx.agent.todo_manager`, `ctx.agent.sub_agent_manager`, and inject into the `task` tool if present.
- `Agent.__init__` must NOT create `TodoManager` or `SubAgentManager`; sets both to `None`.
- The existing `TaskTool` 4-line injection block in `Agent.__init__` is REMOVED.
- `_initialize_async_plugins()` activates `subagent` between `mcp` and `activate_all`.
- CLI smoke test must invoke `merco run --help` via `typer.testing.CliRunner` and assert exit code 0 with `Usage:` in stdout.
- The CLI itself remains a sync `Agent()`-based path; do NOT convert `_setup_agent` to async in this plan.
- Plugin activation is idempotent (already done in 3.1).

---

## File Structure

- `merco/plugins/builtin/subagent/__init__.py`
  - Package export for `SubAgentPlugin`.

- `merco/plugins/builtin/subagent/plugin.py`
  - Defines `SubAgentPlugin`. Creates `TodoManager` + `SubAgentManager` and injects `task` tool.

- `merco/core/agent.py`
  - Removes direct `TodoManager` / `SubAgentManager` creation from `__init__`.
  - Removes the 4-line `TaskTool` injection block.
  - Sets `self.todo_manager = None` and `self.sub_agent_manager = None`.
  - Imports and registers `SubAgentPlugin`.
  - Activates `subagent` in `_initialize_async_plugins()`.

- `tests/plugins/test_subagent_plugin.py`
  - Unit tests for `SubAgentPlugin`.

- `tests/core/test_agent.py`
  - Adds factory path coverage for `agent.todo_manager` / `agent.sub_agent_manager` / task tool injection.

- `tests/cli/test_cli_help.py`
  - New CLI smoke test. Validates `merco run --help`, `merco --help`, `merco init --help`.

- `docs/project-vision/references/architecture-refactor-plan.md`
  - Mark 3.4 complete.

---

### Task 1: CLI e2e smoke test (catches import-time regressions)

**Files:**
- Create: `tests/cli/test_cli_help.py`

**Interfaces:**
- Consumes: `cli.main.app` (Typer application).
- Produces: 3 test functions that invoke CLI `--help` via `typer.testing.CliRunner`.

- [ ] **Step 1: Write the failing CLI smoke tests**

Create `tests/cli/test_cli_help.py`:

```python
"""CLI smoke tests — verifies `merco run --help` boots without import errors.

Phase 3 lesson: unit + mock-LLM integration tests do not cover import-time
errors (e.g., `cli/main.py` passing a removed `skill_registry` kwarg into
`Agent(...)`). These tests exercise the real CLI bootstrap path via
`typer.testing.CliRunner` but only check Typer help output, not the LLM
call path.
"""

import pytest
from typer.testing import CliRunner


@pytest.fixture
def cli_runner():
    return CliRunner()


def test_merco_run_help_succeeds(cli_runner):
    """`merco run --help` boots, exits 0, prints Usage."""
    from cli.main import app

    result = cli_runner.invoke(app, ["run", "--help"])

    assert result.exit_code == 0, (
        f"stdout={result.stdout!r} "
        f"stderr={getattr(result, 'stderr', None) or ''!r}"
    )
    assert "Usage:" in result.stdout


def test_merco_root_help_succeeds(cli_runner):
    """`merco --help` boots without errors."""
    from cli.main import app

    result = cli_runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "Usage:" in result.stdout


def test_merco_init_help_succeeds(cli_runner):
    """`merco init --help` boots without errors."""
    from cli.main import app

    result = cli_runner.invoke(app, ["init", "--help"])

    assert result.exit_code == 0
    assert "Usage:" in result.stdout
```

- [ ] **Step 2: Run tests to verify they pass on the current code**

Run:

```bash
python -m pytest tests/cli/test_cli_help.py -v --tb=short
```

Expected: all 3 PASS (this confirms CLI is currently bootable for `--help`; the 5c57bc0 fix already resolved the import error).

If a test fails with a `TypeError` or import error, do NOT patch the CLI in this task — that would scope-creep. Instead, record the failure and stop. The 3.4 plan assumes the CLI is already bootable.

- [ ] **Step 3: Commit Task 1**

```bash
git add tests/cli/test_cli_help.py
git commit -m "test: add cli help smoke tests"
```

---

### Task 2: Add SubAgentPlugin and unit tests

**Files:**
- Create: `merco/plugins/builtin/subagent/__init__.py`
- Create: `merco/plugins/builtin/subagent/plugin.py`
- Create: `tests/plugins/test_subagent_plugin.py`

**Interfaces:**
- Consumes: `PluginContext` (with `agent`, `agent_profiles`, `config`, `tool_registry`).
- Produces:
  - `SubAgentPlugin.name == "subagent"`
  - `SubAgentPlugin.version == "1.0.0"`
  - `SubAgentPlugin.activate(ctx)` creates `TodoManager` + `SubAgentManager` and wires `task` tool.

- [ ] **Step 1: Write failing SubAgentPlugin tests**

Create `tests/plugins/test_subagent_plugin.py`:

```python
"""SubAgent plugin tests."""

import pytest

from merco.plugins.base import PluginContext
from merco.plugins.builtin.subagent.plugin import SubAgentPlugin
from merco.todo.manager import TodoManager
from merco.agents.subagent import SubAgentManager


class FakeTaskTool:
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
    from merco.plugins.base import PluginContext

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
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
python -m pytest tests/plugins/test_subagent_plugin.py -v --tb=short
```

Expected: FAIL with `ModuleNotFoundError: No module named 'merco.plugins.builtin.subagent'`.

- [ ] **Step 3: Implement SubAgentPlugin**

Create `merco/plugins/builtin/subagent/plugin.py`:

```python
"""SubAgent plugin — creates TodoManager + SubAgentManager and wires TaskTool."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from merco.plugins.base import Plugin

if TYPE_CHECKING:
    from merco.plugins.base import PluginContext

logger = logging.getLogger("merco.plugins.subagent")


class SubAgentPlugin(Plugin):
    """Creates todo manager, sub-agent manager, and wires TaskTool."""

    name = "subagent"
    version = "1.0.0"
    description = "Creates sub-agent dispatch and todo manager"

    async def activate(self, ctx: "PluginContext") -> None:
        from merco.todo.manager import TodoManager
        from merco.agents.subagent import SubAgentManager

        todo_manager = TodoManager(f"{ctx.config.memory_path}/../todos.db")
        sub_agent_manager = SubAgentManager(ctx.agent, ctx.agent_profiles)

        ctx.todo_manager = todo_manager
        ctx.sub_agent_manager = sub_agent_manager
        if ctx.agent is not None:
            ctx.agent.todo_manager = todo_manager
            ctx.agent.sub_agent_manager = sub_agent_manager

        task_tool = ctx.tool_registry.get("task")
        if task_tool is not None:
            if hasattr(task_tool, "_todo_manager"):
                task_tool._todo_manager = todo_manager
            if hasattr(task_tool, "_sub_agent_manager"):
                task_tool._sub_agent_manager = sub_agent_manager

        logger.info("SubAgent plugin activated")
```

Create `merco/plugins/builtin/subagent/__init__.py`:

```python
"""SubAgent built-in plugin."""

from .plugin import SubAgentPlugin

__all__ = ["SubAgentPlugin"]
```

- [ ] **Step 4: Run SubAgentPlugin tests**

Run:

```bash
python -m pytest tests/plugins/test_subagent_plugin.py -v --tb=short
```

Expected: 7 passed.

- [ ] **Step 5: Run existing plugin suite**

Run:

```bash
python -m pytest tests/plugins/ -v --tb=short
```

Expected: all pass.

- [ ] **Step 6: Commit Task 2**

```bash
git add merco/plugins/builtin/subagent/__init__.py merco/plugins/builtin/subagent/plugin.py tests/plugins/test_subagent_plugin.py
git commit -m "feat: add subagent plugin"
```

---

### Task 3: Wire SubAgentPlugin into Agent factory path

**Files:**
- Modify: `merco/core/agent.py`
- Modify: `tests/core/test_agent.py`

**Interfaces:**
- Consumes: `SubAgentPlugin` from Task 2.
- Produces:
  - `Agent.__init__` sets `self.todo_manager = None` and `self.sub_agent_manager = None`; no construction.
  - The 4-line `TaskTool` injection block is removed.
  - `_initialize_async_plugins()` activates `subagent` between `mcp` and `activate_all`.
  - `SubAgentPlugin` registered alongside other builtins.

- [ ] **Step 1: Add failing factory test for sub-agent and task-tool injection**

Append to `tests/core/test_agent.py`:

```python


@pytest.mark.asyncio
async def test_agent_create_initializes_sub_agent_manager(monkeypatch, tmp_path):
    """Agent.create initializes SubAgentManager via SubAgentPlugin."""
    from merco.core.agent import Agent
    from merco.core.config import MercoConfig
    from merco.agents.subagent import SubAgentManager
    from merco.todo.manager import TodoManager
    from tests.conftest import MockLLMClient, make_test_registry

    db_path = str(tmp_path / "factory_subagent.db")
    monkeypatch.setattr("merco.core.agent.LLMClient", MockLLMClient)
    monkeypatch.setattr("merco.core.agent._get_db_path", lambda: db_path)

    cfg = MercoConfig()
    cfg.model.api_key = "test-key"
    cfg.model.model = "test-model"
    cfg.sandbox_mode = "auto"
    cfg.memory_path = str(tmp_path / "memory")

    agent = await Agent.create(config=cfg, tool_registry=make_test_registry())

    assert isinstance(agent.todo_manager, TodoManager)
    assert isinstance(agent.sub_agent_manager, SubAgentManager)
    assert "subagent" in agent.plugin_manager.active_plugins


@pytest.mark.asyncio
async def test_agent_create_injects_managers_into_task_tool(monkeypatch, tmp_path):
    """Agent.create injects todo_manager and sub_agent_manager into the task tool."""
    from merco.core.agent import Agent
    from merco.core.config import MercoConfig
    from tests.conftest import MockLLMClient, make_test_registry

    db_path = str(tmp_path / "factory_tasktool.db")
    monkeypatch.setattr("merco.core.agent.LLMClient", MockLLMClient)
    monkeypatch.setattr("merco.core.agent._get_db_path", lambda: db_path)

    cfg = MercoConfig()
    cfg.model.api_key = "test-key"
    cfg.model.model = "test-model"
    cfg.sandbox_mode = "auto"
    cfg.memory_path = str(tmp_path / "memory")

    agent = await Agent.create(config=cfg, tool_registry=make_test_registry())
    task_tool = agent.tool_registry.get("task")

    assert task_tool is not None
    assert task_tool._todo_manager is agent.todo_manager
    assert task_tool._sub_agent_manager is agent.sub_agent_manager
```

- [ ] **Step 2: Run factory tests to verify failure**

Run:

```bash
python -m pytest tests/core/test_agent.py::test_agent_create_initializes_sub_agent_manager tests/core/test_agent.py::test_agent_create_injects_managers_into_task_tool -v --tb=short
```

Expected: FAIL because:
- `SubAgentPlugin` is not registered or activated.
- `agent.todo_manager` is None on legacy path or the plugin does not exist.

- [ ] **Step 3: Modify Agent**

In `merco/core/agent.py`:

**3a.** Remove the TodoManager/SubAgentManager hard construction. Find:

```python
        ──
        from merco.todo.manager import TodoManager
        from # ── Todo + SubAgent 系统 merco.agents.subagent import SubAgentManager

        self.todo_manager = TodoManager(f"{config.memory_path}/../todos.db")
        self.sub_agent_manager = SubAgentManager(self, self.agent_profiles)
```

Replace with:

```python
        # Todo + SubAgent 由 SubAgentPlugin 激活时创建
        self.todo_manager = None
        self.sub_agent_manager = None
```

**3b.** Remove the TaskTool 4-line injection block. Find:

```python
        # 注入到 TaskTool（全局 tool_registry 中的 TaskTool 实例）
        task_tool = self.tool_registry.get("task")
        if task_tool:
            task_tool._todo_manager = self.todo_manager
            task_tool._sub_agent_manager = self.sub_agent_manager
```

Delete this entire block.

**3c.** Add `SubAgentPlugin` import near the other plugin imports:

```python
from merco.plugins.builtin.subagent.plugin import SubAgentPlugin
```

**3d.** Register `SubAgentPlugin` between `MCPPlugin` and `SuperpowerPlugin`:

```python
self.plugin_manager.register(ObservabilityPlugin())
self.plugin_manager.register(SkillPlugin())
self.plugin_manager.register(MCPPlugin())
self.plugin_manager.register(SubAgentPlugin())
self.plugin_manager.register(SuperpowerPlugin())
```

**3e.** Update `_initialize_async_plugins()` to activate subagent between mcp and activate_all:

```python
async def _initialize_async_plugins(self) -> None:
    """Initialize plugins in deterministic order for Agent.create()."""
    await self.plugin_manager.activate("observability")
    self.observer = self._plugin_ctx.observer
    assert self.observer is not None
    self._restore_context()
    await self.plugin_manager.activate("skills")
    await self.plugin_manager.activate("mcp")
    await self.plugin_manager.activate("subagent")
    await self.plugin_manager.activate_all()
```

- [ ] **Step 4: Run factory tests**

Run:

```bash
python -m pytest tests/core/test_agent.py::test_agent_create_initializes_sub_agent_manager tests/core/test_agent.py::test_agent_create_injects_managers_into_task_tool -v --tb=short
```

Expected: 2 passed.

- [ ] **Step 5: Run focused regressions**

Run:

```bash
python -m pytest tests/core/test_agent.py tests/agents/ tests/plugins/ tests/integration/test_todo_subagent.py tests/integration/test_agent_loop.py tests/cli/test_cli_help.py -v --tb=short
```

Expected: all selected tests pass.

- [ ] **Step 6: Commit Task 3**

```bash
git add merco/core/agent.py tests/core/test_agent.py
git commit -m "refactor: wire subagent plugin into agent factory"
```

---

### Task 4: Full regression and roadmap update

**Files:**
- Modify: `docs/project-vision/references/architecture-refactor-plan.md`

**Interfaces:**
- Consumes: Tasks 1-3 complete.
- Produces: documented 3.4 status as complete.

- [ ] **Step 1: Run focused regression suite**

Run:

```bash
python -m pytest tests/plugins/ tests/core/test_agent.py tests/agents/ tests/mcp/ tests/integration/test_agent_loop.py tests/integration/test_todo_subagent.py tests/integration/test_interrupt_flow.py tests/core/test_interrupt.py tests/cli/test_cli_help.py tests/observability/test_observer.py -v --tb=short
```

Expected: all selected tests pass.

- [ ] **Step 2: Run full suite and confirm no new failures**

Run:

```bash
python -m pytest tests/ -q --tb=line
```

Expected: same 9 pre-existing failures from before 3.4; no new failures introduced by SubAgentPlugin migration.

- [ ] **Step 3: Update architecture roadmap status**

In `docs/project-vision/references/architecture-refactor-plan.md`, change section 3.4 from:

```markdown
### 3.4 agents + todo → SubAgentPlugin
```

to:

```markdown
### 3.4 agents + todo → SubAgentPlugin ✅ 已完成
```

Add one sentence after the migration table:

```markdown
`SubAgentPlugin` 负责创建 TodoManager + SubAgentManager 并注入 TaskTool；新增 CLI e2e smoke test 防止 import-time 回归。
```

- [ ] **Step 4: Verify docs diff**

Run:

```bash
git diff -- docs/project-vision/references/architecture-refactor-plan.md
```

Expected: only 3.4 status and the e2e test note changed.

- [ ] **Step 5: Commit Task 4**

```bash
git add docs/project-vision/references/architecture-refactor-plan.md
git commit -m "docs: mark subagent plugin migration complete"
```

---

## Plan Self-Review

Spec coverage:
- CLI e2e smoke test (3 help tests): Task 1.
- SubAgentPlugin class and file path: Task 2.
- SubAgentPlugin creates `TodoManager` + `SubAgentManager` + TaskTool injection: Task 2.
- `Agent.__init__` no longer creates TodoManager / SubAgentManager: Task 3.
- 4-line TaskTool injection block removed: Task 3.
- `_initialize_async_plugins` activates `subagent` between `mcp` and `activate_all`: Task 3.
- `SubAgentPlugin` registered: Task 3.
- Roadmap status update: Task 4.

Placeholder scan:
- No TBD/TODO/fill-in placeholders.
- Every code-changing step has exact code.
- Every test step has exact command and expected result.

Type consistency:
- `SubAgentPlugin` name/version/description consistent.
- `_initialize_async_plugins` activation order consistent: observability → restore → skills → mcp → subagent → activate_all.
- TaskTool injection uses `hasattr` defensively, consistent with prior plugins (3.1/3.2/3.3).
