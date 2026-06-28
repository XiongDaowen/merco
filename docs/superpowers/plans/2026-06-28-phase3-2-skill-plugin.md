# Phase 3.2 SkillPlugin Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make SkillPlugin the sole owner of `SkillRegistry` initialization and inject it into both the agent and the `SkillViewTool`, while migrating the production internal sub-agent creation path to `Agent.create(...)`.

**Architecture:** Add a built-in `SkillPlugin` that creates and loads `SkillRegistry` from `ctx.config.skills_paths`, syncs the registry to `agent.skill_registry`, and injects into `SkillViewTool`. Extend `PluginContext` with `agent` and `skill_registry`. Remove `skill_registry` from `Agent.__init__` and migrate `SubAgentManager._create_sub_agent` from sync `Agent(...)` to async `await Agent.create(...)`.

**Tech Stack:** Python 3.12, pytest, pytest-asyncio, existing merco Plugin/Agent fixtures.

## Global Constraints

- TDD is mandatory: write failing test, verify failure, implement minimal code, verify pass.
- Do not begin 3.3-3.6 plugin migration in this plan.
- `Agent.__init__` must NOT accept `skill_registry` as a parameter.
- `SkillPlugin` is the only initialization path for `SkillRegistry` (no fallback, no factory other than the plugin).
- `SkillPlugin.activate(ctx)` must set `ctx.skill_registry`, `ctx.agent.skill_registry`, and inject the registry into the `skill_view` tool if present.
- `SkillsHintChunk` continues to read `agent.skill_registry`; do not change its interface.
- `SubAgentManager._create_sub_agent` becomes async and uses `await Agent.create(...)`.
- Production `Agent.create(...)` is the path that loads skills. Legacy `Agent(...)` remains constructible for existing test fixtures, but its `skill_registry` starts as `None`.
- Plugin activation is idempotent (already done in 3.1).

---

## File Structure

- `merco/plugins/builtin/skills/__init__.py`
  - Package export for SkillPlugin.

- `merco/plugins/builtin/skills/plugin.py`
  - Defines `SkillPlugin`.

- `merco/plugins/base.py`
  - Adds `agent` and `skill_registry` optional fields to `PluginContext`.

- `merco/core/agent.py`
  - Removes `skill_registry` parameter from `__init__`.
  - Sets `self.skill_registry = None` in `__init__`.
  - Removes `skill_registry` parameter from `Agent.create(...)`.
  - Sets `ctx.agent = self` so SkillPlugin can reach the parent agent.
  - Activates `skills` plugin in `_initialize_async_plugins()`.
  - Registers SkillPlugin alongside ObservabilityPlugin.

- `merco/agents/subagent.py`
  - `_create_sub_agent` becomes async.
  - Uses `await Agent.create(...)`.

- `tests/plugins/test_skill_plugin.py`
  - Unit tests for SkillPlugin.

- `tests/core/test_agent.py`
  - Agent.create factory path tests for skills.

- `tests/agents/test_subagent.py`
  - Verifies async sub-agent creation still works.

---

### Task 1: Add SkillPlugin and extend PluginContext

**Files:**
- Create: `tests/plugins/test_skill_plugin.py`
- Create: `merco/plugins/builtin/skills/__init__.py`
- Create: `merco/plugins/builtin/skills/plugin.py`
- Modify: `merco/plugins/base.py`

**Interfaces:**
- Consumes: `PluginContext`, `HookRegistry`, `SkillRegistry`.
- Produces:
  - `SkillPlugin.name == "skills"`
  - `SkillPlugin.version == "1.0.0"`
  - `SkillPlugin.activate(ctx) -> None`
  - `PluginContext(..., agent=None, skill_registry=None)` is valid.

- [ ] **Step 1: Write failing plugin tests**

Create `tests/plugins/test_skill_plugin.py`:

```python
"""Skill plugin tests."""

import pytest

from merco.plugins.base import PluginContext
from merco.plugins.builtin.skills.plugin import SkillPlugin
from merco.skills.registry import SkillRegistry


class FakeSkillTool:
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
    ctx.tool_registry.register(fake_tool)  # type: ignore[arg-type]

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
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
python -m pytest tests/plugins/test_skill_plugin.py -v --tb=short
```

Expected: FAIL with `ModuleNotFoundError: No module named 'merco.plugins.builtin.skills'` or `TypeError` because `PluginContext` does not accept `agent`/`skill_registry`.

- [ ] **Step 3: Implement PluginContext extension and SkillPlugin**

In `merco/plugins/base.py`:

1. Update the `PluginContext.__init__` signature to add the new optional fields at the end:

```python
def __init__(
    self,
    hooks: "HookRegistry",
    tool_registry: "ToolRegistry",
    prompt_builder: "PromptBuilder",
    recovery_pipeline: "RecoveryPipeline",
    result_pipeline: "ResultPipeline",
    memory_save_pipeline: "MemorySavePipeline",
    recaller: "HybridRecaller",
    config: "MercoConfig",
    observer: "Observer" = None,
    todo_manager: "TodoManager" = None,
    sub_agent_manager: "SubAgentManager" = None,
    context_pipeline: "ContextPipeline" = None,
    agent_profiles: "AgentProfileRegistry" = None,
    memory_backends: "MemoryBackendRegistry" = None,
    loop_policies: "LoopPolicyRegistry" = None,
    agent: "Agent" = None,
    skill_registry: "SkillRegistry" = None,
):
```

Add `SkillRegistry` to the `TYPE_CHECKING` imports at the top:

```python
from merco.skills.registry import SkillRegistry
```

2. Add `self.agent = agent` and `self.skill_registry = skill_registry` lines inside `__init__`.

Create `merco/plugins/builtin/skills/plugin.py`:

```python
"""Skill plugin — creates and loads SkillRegistry."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from merco.plugins.base import Plugin

if TYPE_CHECKING:
    from merco.plugins.base import PluginContext

logger = logging.getLogger("merco.plugins.skills")


class SkillPlugin(Plugin):
    """Creates SkillRegistry and injects it into the agent and skill_view tool."""

    name = "skills"
    version = "1.0.0"
    description = "Loads skills and injects the skill registry"

    async def activate(self, ctx: "PluginContext") -> None:
        from merco.skills.registry import SkillRegistry

        registry = SkillRegistry()
        registry.load_from_paths(ctx.config.skills_paths)

        ctx.skill_registry = registry
        if ctx.agent is not None:
            ctx.agent.skill_registry = registry

        skill_tool = ctx.tool_registry.get("skill_view")
        if skill_tool is not None and hasattr(skill_tool, "set_skill_registry"):
            skill_tool.set_skill_registry(registry)

        logger.info("Skill plugin activated (paths=%s)", ctx.config.skills_paths)
```

Create `merco/plugins/builtin/skills/__init__.py`:

```python
"""Skill built-in plugin."""

from .plugin import SkillPlugin

__all__ = ["SkillPlugin"]
```

- [ ] **Step 4: Run plugin tests**

Run:

```bash
python -m pytest tests/plugins/test_skill_plugin.py -v --tb=short
```

Expected: 6 passed.

- [ ] **Step 5: Run existing plugin tests**

Run:

```bash
python -m pytest tests/plugins/ -v --tb=short
```

Expected: existing plugin tests plus new tests pass.

- [ ] **Step 6: Commit Task 1**

```bash
git add merco/plugins/base.py merco/plugins/builtin/skills/__init__.py merco/plugins/builtin/skills/plugin.py tests/plugins/test_skill_plugin.py
git commit -m "feat: add skill plugin and ctx.skill_registry"
```

---

### Task 2: Wire SkillPlugin into Agent and migrate Agent.create to load skills

**Files:**
- Modify: `merco/core/agent.py`
- Modify: `tests/core/test_agent.py`

**Interfaces:**
- Consumes: `SkillPlugin` from Task 1.
- Produces:
  - `Agent.__init__(..., skill_registry=None)` parameter REMOVED.
  - `self.skill_registry = None` in `__init__`.
  - `Agent.create(cls, config, tool_registry=None)` — `skill_registry` parameter REMOVED.
  - `_initialize_async_plugins()` activates `skills` plugin.
  - `ctx.agent` is set to `self`.
  - `SkillPlugin` registered before `activate_all()`.

- [ ] **Step 1: Add failing Agent.create skills tests**

Append to `tests/core/test_agent.py`:

```python


@pytest.mark.asyncio
async def test_agent_create_initializes_skill_registry(monkeypatch, tmp_path):
    """Agent.create loads SkillRegistry via SkillPlugin."""
    from merco.core.agent import Agent
    from merco.core.config import MercoConfig
    from merco.skills.registry import SkillRegistry
    from tests.conftest import MockLLMClient, make_test_registry

    db_path = str(tmp_path / "factory_skills.db")
    monkeypatch.setattr("merco.core.agent.LLMClient", MockLLMClient)
    monkeypatch.setattr("merco.core.agent._get_db_path", lambda: db_path)

    cfg = MercoConfig()
    cfg.model.api_key = "test-key"
    cfg.model.model = "test-model"
    cfg.sandbox_mode = "auto"
    cfg.memory_path = str(tmp_path / "memory")
    cfg.skills_paths = []  # ensure paths list exists

    agent = await Agent.create(config=cfg, tool_registry=make_test_registry())

    assert isinstance(agent.skill_registry, SkillRegistry)
    assert "skills" in agent.plugin_manager.active_plugins


@pytest.mark.asyncio
async def test_agent_create_injects_skill_registry_into_skill_view_tool(monkeypatch, tmp_path):
    """Agent.create makes SkillViewTool aware of the registry."""
    from merco.core.agent import Agent
    from merco.core.config import MercoConfig
    from merco.tools.skill_tools import SkillViewTool
    from tests.conftest import MockLLMClient, make_test_registry

    db_path = str(tmp_path / "factory_skill_view.db")
    monkeypatch.setattr("merco.core.agent.LLMClient", MockLLMClient)
    monkeypatch.setattr("merco.core.agent._get_db_path", lambda: db_path)

    cfg = MercoConfig()
    cfg.model.api_key = "test-key"
    cfg.model.model = "test-model"
    cfg.sandbox_mode = "auto"
    cfg.memory_path = str(tmp_path / "memory")
    cfg.skills_paths = []

    agent = await Agent.create(config=cfg, tool_registry=make_test_registry())
    skill_tool = agent.tool_registry.get("skill_view")

    assert skill_tool is not None
    assert isinstance(skill_tool, SkillViewTool)
    assert skill_tool._skill_registry is agent.skill_registry


def test_agent_init_no_longer_accepts_skill_registry(monkeypatch, tmp_path):
    """Agent.__init__ rejects skill_registry keyword argument."""
    from merco.core.agent import Agent
    from merco.core.config import MercoConfig
    from tests.conftest import MockLLMClient

    db_path = str(tmp_path / "factory_init_kw.db")
    monkeypatch.setattr("merco.core.agent.LLMClient", MockLLMClient)
    monkeypatch.setattr("merco.core.agent._get_db_path", lambda: db_path)

    cfg = MercoConfig()
    cfg.model.api_key = "test-key"
    cfg.model.model = "test-model"
    cfg.sandbox_mode = "auto"
    cfg.memory_path = str(tmp_path / "memory")

    with pytest.raises(TypeError):
        Agent(config=cfg, skill_registry=object())  # type: ignore[call-arg]
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
python -m pytest tests/core/test_agent.py::test_agent_create_initializes_skill_registry tests/core/test_agent.py::test_agent_create_injects_skill_registry_into_skill_view_tool tests/core/test_agent.py::test_agent_init_no_longer_accepts_skill_registry -v --tb=short
```

Expected: FAIL because:
- `agent.skill_registry` is still None (plugin not wired)
- `Agent.__init__` still accepts `skill_registry`

- [ ] **Step 3: Modify Agent to remove skill_registry parameter and activate skills plugin**

In `merco/core/agent.py`:

1. Change `Agent.__init__` signature from:

```python
def __init__(self, config: MercoConfig, tool_registry=None, skill_registry=None, _defer_plugin_init: bool = False):
    self.config = config
    self.session = Session()
    from merco.sandbox import snapshot
    snapshot.set_current_session(self.session.id)
    self.context = ContextManager(max_tokens=config.max_input_tokens)
    self.tool_registry = tool_registry
    self.skill_registry = skill_registry
```

to:

```python
def __init__(self, config: MercoConfig, tool_registry=None, _defer_plugin_init: bool = False):
    self.config = config
    self.session = Session()
    from merco.sandbox import snapshot
    snapshot.set_current_session(self.session.id)
    self.context = ContextManager(max_tokens=config.max_input_tokens)
    self.tool_registry = tool_registry
    self.skill_registry = None
```

2. After the line that builds `self._plugin_ctx`, set the agent reference on ctx. Find the existing block ending with `self.plugin_manager = PluginManager(self._plugin_ctx)` and add this immediately after:

```python
self._plugin_ctx.agent = self
```

3. Update the `Agent.create` classmethod. Change from:

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
```

to:

```python
@classmethod
async def create(cls, config: MercoConfig, tool_registry=None) -> "Agent":
    """Create an Agent with deterministic async plugin initialization."""
    agent = cls(
        config=config,
        tool_registry=tool_registry,
        _defer_plugin_init=True,
    )
    await agent._initialize_async_plugins()
    return agent
```

4. Add `SkillPlugin` import near the existing ObservabilityPlugin import:

```python
from merco.plugins.builtin.observability.plugin import ObservabilityPlugin
from merco.plugins.builtin.skills.plugin import SkillPlugin
from merco.plugins.builtin.superpower.plugin import SuperpowerPlugin
```

5. Register `SkillPlugin` alongside ObservabilityPlugin and SuperpowerPlugin:

```python
self.plugin_manager.register(ObservabilityPlugin())
self.plugin_manager.register(SkillPlugin())
self.plugin_manager.register(SuperpowerPlugin())
```

6. Update `_initialize_async_plugins()` to activate skills. Change from:

```python
async def _initialize_async_plugins(self) -> None:
    """Initialize plugins in deterministic order for Agent.create()."""
    await self.plugin_manager.activate("observability")
    self.observer = self._plugin_ctx.observer
    assert self.observer is not None
    self._restore_context()
    await self.plugin_manager.activate_all()
```

to:

```python
async def _initialize_async_plugins(self) -> None:
    """Initialize plugins in deterministic order for Agent.create()."""
    await self.plugin_manager.activate("observability")
    self.observer = self._plugin_ctx.observer
    assert self.observer is not None
    self._restore_context()
    await self.plugin_manager.activate("skills")
    await self.plugin_manager.activate_all()
```

- [ ] **Step 4: Run factory tests**

Run:

```bash
python -m pytest tests/core/test_agent.py::test_agent_create_initializes_skill_registry tests/core/test_agent.py::test_agent_create_injects_skill_registry_into_skill_view_tool tests/core/test_agent.py::test_agent_init_no_longer_accepts_skill_registry -v --tb=short
```

Expected: 3 passed.

- [ ] **Step 5: Run focused Agent regressions**

Run:

```bash
python -m pytest tests/core/test_agent.py tests/integration/test_agent_loop.py tests/observability/test_observer.py tests/plugins/ -v --tb=short
```

Expected: all selected tests pass.

- [ ] **Step 6: Commit Task 2**

```bash
git add merco/core/agent.py tests/core/test_agent.py
git commit -m "refactor: wire skill plugin into agent factory"
```

---

### Task 3: Migrate SubAgentManager to async Agent.create

**Files:**
- Modify: `merco/agents/subagent.py`
- Modify: `tests/agents/test_subagent.py`

**Interfaces:**
- Consumes: `Agent.create(...)` from Task 2.
- Produces:
  - `SubAgentManager._create_sub_agent(...)` is `async`.
  - Internal `Agent(...)` call replaced with `await Agent.create(...)`.

- [ ] **Step 1: Update SubAgent tests to await the sub-agent creation**

Look at `tests/agents/test_subagent.py`. Wherever `TestSubAgentManager` or other tests call `SubAgentManager.dispatch(...)` and expect the sub-agent path to be invoked, mark them async if they are not already:

```python
@pytest.mark.asyncio
async def test_create_sub_agent_via_factory():
    ...
```

If any test currently constructs `SubAgentManager._create_sub_agent(...)` synchronously, change it to:

```python
sub_agent = await sub_agent_manager._create_sub_agent("default")
```

- [ ] **Step 2: Run sub-agent tests to verify they fail with sync _create_sub_agent**

Run:

```bash
python -m pytest tests/agents/test_subagent.py tests/agents/test_subagent_profile.py -v --tb=short
```

Expected: tests calling the sub-agent creation should report a coroutine warning or fail with `TypeError: object coroutine is not callable`, depending on the test surface.

- [ ] **Step 3: Update SubAgentManager._create_sub_agent to async**

In `merco/agents/subagent.py`, change the method signature and the inner `Agent(...)` call:

Replace:

```python
def _create_sub_agent(self, agent_name: str) -> "Agent":
    """创建子代理，根据 profile 配置 prompt/tools/model/limits"""
    from merco.core.agent import Agent
    from merco.core.session import Session
    from merco.agents.profile import ProfilePromptChunk
    from merco.tools.registry import ToolRegistry

    # 查找 profile
    profile = None
    if self._profiles:
        profile = self._profiles.get(agent_name) or self._profiles.get("default")

    config = self._parent.config
    tool_registry = self._parent.tool_registry

    if profile:
        # model override
        if profile.model:
            import copy
            config = copy.deepcopy(config)
            config.model.provider = profile.model.get("provider", config.model.provider)
            config.model.model = profile.model.get("model", config.model.model)

        # tools allowlist
        if profile.tools:
            tool_registry = ToolRegistry()
            for name in profile.tools:
                tool = self._parent.tool_registry.get(name)
                if tool:
                    tool_registry.register(tool)

    sub_agent = Agent(config=config, tool_registry=tool_registry)
    # 强制新 session（Agent.__init__ 会 resume_or_create 恢复父会话）
    sub_agent.session = Session(store=sub_agent._session_store)
    sub_agent._session_store.create_session(sub_agent.session.id)

    if profile:
        sub_agent.prompt_builder.use(ProfilePromptChunk(profile))
        if profile.limits.get("max_tool_calls"):
            sub_agent.config.max_tool_calls = profile.limits["max_tool_calls"]
            sub_agent._max_tool_calls = profile.limits["max_tool_calls"]

    self._active[sub_agent.session.id] = sub_agent
    return sub_agent
```

with:

```python
async def _create_sub_agent(self, agent_name: str) -> "Agent":
    """创建子代理，根据 profile 配置 prompt/tools/model/limits"""
    from merco.core.agent import Agent
    from merco.core.session import Session
    from merco.agents.profile import ProfilePromptChunk
    from merco.tools.registry import ToolRegistry

    # 查找 profile
    profile = None
    if self._profiles:
        profile = self._profiles.get(agent_name) or self._profiles.get("default")

    config = self._parent.config
    tool_registry = self._parent.tool_registry

    if profile:
        # model override
        if profile.model:
            import copy
            config = copy.deepcopy(config)
            config.model.provider = profile.model.get("provider", config.model.provider)
            config.model.model = profile.model.get("model", config.model.model)

        # tools allowlist
        if profile.tools:
            tool_registry = ToolRegistry()
            for name in profile.tools:
                tool = self._parent.tool_registry.get(name)
                if tool:
                    tool_registry.register(tool)

    sub_agent = await Agent.create(config=config, tool_registry=tool_registry)
    # 强制新 session（Agent.create 会 resume_or_create 恢复父会话）
    sub_agent.session = Session(store=sub_agent._session_store)
    sub_agent._session_store.create_session(sub_agent.session.id)

    if profile:
        sub_agent.prompt_builder.use(ProfilePromptChunk(profile))
        if profile.limits.get("max_tool_calls"):
            sub_agent.config.max_tool_calls = profile.limits["max_tool_calls"]
            sub_agent._max_tool_calls = profile.limits["max_tool_calls"]

    self._active[sub_agent.session.id] = sub_agent
    return sub_agent
```

Also update the call site inside `dispatch()`. Change:

```python
sub_agent = self._create_sub_agent(agent_name)
```

to:

```python
sub_agent = await self._create_sub_agent(agent_name)
```

- [ ] **Step 4: Update tests to await sub-agent creation**

For every test in `tests/agents/test_subagent.py` and `tests/agents/test_subagent_profile.py` that:

- Calls `sub_agent_manager.dispatch(...)` synchronously → wrap as `@pytest.mark.asyncio` and `await`.
- Calls `sub_agent_manager._create_sub_agent(...)` synchronously → make async with `await`.

If a test currently does:

```python
def test_dispatch_updates_todo():
    sub_agent = SubAgentManager(parent, profiles)
    sub_agent.dispatch(...)
```

Change to:

```python
@pytest.mark.asyncio
async def test_dispatch_updates_todo():
    sub_agent = SubAgentManager(parent, profiles)
    await sub_agent.dispatch(...)
```

- [ ] **Step 5: Run sub-agent tests**

Run:

```bash
python -m pytest tests/agents/test_subagent.py tests/agents/test_subagent_profile.py tests/integration/test_todo_subagent.py -v --tb=short
```

Expected: all selected tests pass.

- [ ] **Step 6: Commit Task 3**

```bash
git add merco/agents/subagent.py tests/agents/test_subagent.py tests/agents/test_subagent_profile.py
git commit -m "refactor: migrate subagent creation to Agent.create"
```

---

### Task 4: Regression verification and roadmap update

**Files:**
- Modify: `docs/project-vision/references/architecture-refactor-plan.md`

**Interfaces:**
- Consumes: Tasks 1-3 complete.
- Produces: documented 3.2 status as complete.

- [ ] **Step 1: Run focused regression suite**

Run:

```bash
python -m pytest tests/plugins/ tests/core/test_agent.py tests/agents/ tests/integration/test_agent_loop.py tests/integration/test_todo_subagent.py tests/observability/test_observer.py -v --tb=short
```

Expected: all selected tests pass.

- [ ] **Step 2: Run full suite and confirm no new failures**

Run:

```bash
python -m pytest tests/ -q --tb=line
```

Expected: same 9 pre-existing failures from before 3.2 (CLI, llm, guard, context compression); no new failures introduced by SkillPlugin migration.

- [ ] **Step 3: Update architecture roadmap status**

In `docs/project-vision/references/architecture-refactor-plan.md`, change section 3.2 from:

```markdown
### 3.2 skills → SkillPlugin
```

to:

```markdown
### 3.2 skills → SkillPlugin ✅ 已完成
```

Add a one-sentence note after the migration table:

```markdown
`SkillPlugin` 负责加载 SkillRegistry 并注入 Agent + SkillViewTool；生产内部创建路径已迁移到 `Agent.create(...)`。
```

- [ ] **Step 4: Verify docs diff**

Run:

```bash
git diff -- docs/project-vision/references/architecture-refactor-plan.md
```

Expected: only 3.2 status and the SkillPlugin note changed.

- [ ] **Step 5: Commit Task 4**

```bash
git add docs/project-vision/references/architecture-refactor-plan.md
git commit -m "docs: mark skill plugin migration complete"
```

---

## Plan Self-Review

Spec coverage:
- SkillPlugin class and file path: Task 1.
- PluginContext `agent` and `skill_registry` extension: Task 1.
- SkillViewTool injection: Task 1.
- `Agent.__init__` no `skill_registry`: Task 2.
- `Agent.create` no `skill_registry`: Task 2.
- `ctx.agent = self` wiring: Task 2.
- Skills plugin activation in `_initialize_async_plugins`: Task 2.
- SubAgentManager async `_create_sub_agent`: Task 3.
- Roadmap status update: Task 4.

Placeholder scan:
- No TBD/TODO placeholders.
- Every code-changing step has exact code.
- Every test step has exact command and expected result.

Type consistency:
- `SkillPlugin` name/version consistent.
- `PluginContext` field names `agent`/`skill_registry` consistent.
- `Agent.create(...)` signature change consistent across spec and tasks.
- `_create_sub_agent` name and async-ness consistent across tasks.
