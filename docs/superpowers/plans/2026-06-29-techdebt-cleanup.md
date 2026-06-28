# Phase 4: Tech Debt Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the dual-path legacy from Phase 3 so that `Agent.create()` is the single initialization entry point, CLI uses it deterministically, and all tests exercise the factory path.

**Architecture:** Delete `_defer_plugin_init`, the fire-and-forget `activate_all()` block, direct `Observer` construction, and hard-coded `_restore_context()` from `Agent.__init__`. Make CLI `_setup_agent` async and use `await Agent.create(...)`. Convert the `test_agent` fixture to an async fixture that calls `await Agent.create(...)`.

**Tech Stack:** Python 3.12, pytest, pytest-asyncio, typer.

## Global Constraints

- TDD is mandatory: only the CLI smoke test guards regressions here (the cleanup itself is tested by passing the existing test suite).
- `Agent.__init__` must NOT perform any async work, activate plugins, or restore context.
- `Agent.create()` is the ONLY supported path to a fully initialized Agent.
- CLI `--help` must continue to work after the migration (`tests/cli/test_cli_help.py`).
- All 436 tests that currently pass must continue to pass.
- Do NOT change plugin implementations, `Agent.run()`, or business logic.

---

### Task 1: Remove Agent.__init__ dual-path (delete _defer_plugin_init, fire-and-forget, legacy observer/restore)

**Files:**
- Modify: `merco/core/agent.py`

**Interfaces:**
- Produces: `Agent.__init__` is sync-only. No `_defer_plugin_init` parameter.

- [ ] **Step 1: Delete the `_defer_plugin_init` parameter and all gates**

In `merco/core/agent.py`:

**1a.** Change constructor signature from:

```python
def __init__(self, config: MercoConfig, tool_registry=None, _defer_plugin_init: bool = False):
```

to:

```python
def __init__(self, config: MercoConfig, tool_registry=None):
```

**1b.** Delete the legacy Observer creation gate. Replace:

```python
        from merco.hooks.registry import HookRegistry
        self.hooks = HookRegistry()
        if _defer_plugin_init:
            self.observer = None
        else:
            from merco.observability.observer import Observer
            self.observer = Observer(self.hooks)
```

with:

```python
        from merco.hooks.registry import HookRegistry
        self.hooks = HookRegistry()
        # Observer 由 ObservabilityPlugin 激活时创建
        self.observer = None
```

**1c.** Delete the legacy `_restore_context()` gate. After the line `self.session = Session.resume_or_create(self._session_store)`, replace:

```python
        if not _defer_plugin_init:
            self._restore_context()
```

with just the comment — remove the `self.session = Session.resume_or_create(...)` line if `_restore_context()` was the only consumer. Actually keep the session line; just delete the conditional restore:

```python
        # _restore_context() 在 Agent.create()._initialize_async_plugins() 中执行
```

(Remove `self._restore_context()` entirely from `__init__`.)

**1d.** Delete the entire fire-and-forget `activate_all()` block. Remove:

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

**1e.** Update `Agent.create()` — remove `_defer_plugin_init=True` from the inner `cls(...)` call:

```python
@classmethod
async def create(cls, config: MercoConfig, tool_registry=None) -> "Agent":
    agent = cls(config=config, tool_registry=tool_registry)
    await agent._initialize_async_plugins()
    return agent
```

- [ ] **Step 2: Run existing Agent tests to verify no breakage**

```bash
python -m pytest tests/core/test_agent.py tests/integration/test_agent_loop.py tests/cli/test_cli_help.py -v --tb=short
```

Expected: all pass (test_agent fixture still works because it already doesn't depend on `_defer_plugin_init`).

- [ ] **Step 3: Run full suite to verify**

```bash
python -m pytest tests/ -q --tb=line
```

Expected: same 9 pre-existing failures.

- [ ] **Step 4: Commit**

```bash
git add merco/core/agent.py
git commit -m "refactor: remove agent init dual-path"
```

---

### Task 2: Migrate CLI to async and use Agent.create()

**Files:**
- Modify: `cli/main.py`

**Interfaces:**
- Consumes: `Agent.create(...)` (now the only path).
- Produces: `_setup_agent` is `async def` and uses `await Agent.create(...)`. Deletes manual SkillRegistry/SkillViewTool hack.

- [ ] **Step 1: Delete manual SkillRegistry fallback code**

In `cli/main.py`, remove lines 198-214 (the SkillRegistry creation, SkillViewTool injection, and `agent.skill_registry = skill_registry` backup). Keep only:

```python
    agent = await Agent.create(config=cfg, tool_registry=tool_registry)
```

**Note:** keep `install_builtin_skills()` above — it installs skill files to disk, which is separate from registry loading and still needed.

- [ ] **Step 2: Make `_setup_agent` async**

Change:

```python
def _setup_agent(config_path, model, api_key, debug):
```

to:

```python
async def _setup_agent(config_path, model, api_key, debug):
```

Change the `Agent(...)` call to:

```python
    agent = await Agent.create(config=cfg, tool_registry=tool_registry)
```

- [ ] **Step 3: Bridge sync callers with asyncio.run()**

In `main_callback`:

```python
agent, dashboard, config_source = asyncio.run(_setup_agent(config, model, api_key, debug))
```

In `run_cmd`:

```python
agent, dashboard, config_source = asyncio.run(_setup_agent(config, model, api_key, debug))
```

- [ ] **Step 4: Verify CLI smoke test**

```bash
python -m pytest tests/cli/test_cli_help.py -v --tb=short
```

Expected: 3 passed.

- [ ] **Step 5: Verify CLI import**

```bash
python -c "from cli.main import app; print('OK')"
```

Expected: OK.

- [ ] **Step 6: Commit**

```bash
git add cli/main.py
git commit -m "refactor: migrate cli to async agent factory"
```

---

### Task 3: Migrate test_agent fixture to Agent.create() + adapt all consuming tests

**Files:**
- Modify: `tests/conftest.py`
- Modify: `tests/agents/test_subagent.py`
- Modify: `tests/agents/test_subagent_profile.py`
- Modify: `tests/core/test_agent.py`
- Modify: `tests/integration/test_agent_profile.py`
- Modify: `tests/integration/test_context_pipeline.py`
- Modify: `tests/integration/test_llm_hooks.py`
- Modify: `tests/integration/test_loop_policy.py`
- Modify: `tests/integration/test_memory_lifecycle.py`
- Modify: `tests/integration/test_scenarios.py`
- Modify: `tests/integration/test_todo_subagent.py`
- Modify: `tests/observability/test_observer.py`
- Modify: `tests/plugins/test_plugin_integration.py`

**Context:** 59 test functions across 12 files use the `test_agent` fixture. Currently `test_agent` is a sync fixture that creates `Agent(...)` via the legacy path. It must become an async fixture that calls `await Agent.create(...)`.

- [ ] **Step 1: Convert the fixture**

In `tests/conftest.py`, change the `test_agent` fixture from sync to async:

```python
@pytest.fixture
async def test_agent(monkeypatch, tmp_path):
    """创建带有 mock LLM + 测试工具 + 临时 session store 的 Agent"""
    db_path = str(tmp_path / "test.db")

    monkeypatch.setattr("merco.core.agent.LLMClient", MockLLMClient)
    monkeypatch.setattr("merco.core.agent._get_db_path", lambda: db_path)

    cfg = MercoConfig()
    cfg.model.api_key = "test-key"
    cfg.model.model = "test-model"
    cfg.sandbox_mode = "auto"
    cfg.memory_path = str(tmp_path / "memory")

    reg = make_test_registry()
    agent = await Agent.create(config=cfg, tool_registry=reg)
    return agent
```

Note: `Agent.create` already activates all registered plugins including SkillPlugin, ObservabilityPlugin, etc. The mock LLM is set before the factory runs, so `_initialize_async_plugins` won't call a real LLM.

- [ ] **Step 2: Convert all 12 consumer test files**

For each of the 12 files listed above, apply this mechanical transformation to every test function that takes `test_agent`:

- If `def test_foo(test_agent, ...):` → add `@pytest.mark.asyncio` as a decorator, and change to `async def test_foo(test_agent, ...):`
- If the test already has `@pytest.mark.asyncio` and `async def`, skip — it's already done.

Example:

```python
# Before:
def test_agent_has_mcp_manager(test_agent):
    assert hasattr(test_agent, 'mcp_manager')
    ...

# After:
@pytest.mark.asyncio
async def test_agent_has_mcp_manager(test_agent):
    assert hasattr(test_agent, 'mcp_manager')
    ...
```

**IMPORTANT:** Do NOT change any test logic or assertions. Only add the decorator and `async` keyword. Do NOT add `await` inside tests that don't already have async calls.

File-by-file details:

1. `tests/agents/test_subagent.py` — 2 tests use `test_agent`
2. `tests/agents/test_subagent_profile.py` — 6 tests (already async, but check decorator)
3. `tests/core/test_agent.py` — ~15 tests use `test_agent` directly or have `agent` that comes from `test_agent`
4. `tests/integration/test_agent_profile.py` — 2 tests (already async)
5. `tests/integration/test_context_pipeline.py` — ~5 tests
6. `tests/integration/test_llm_hooks.py` — 3 tests (already async via `@pytest.mark.asyncio`)
7. `tests/integration/test_loop_policy.py` — ~4 tests
8. `tests/integration/test_memory_lifecycle.py` — ~3 tests
9. `tests/integration/test_scenarios.py` — ~2 tests
10. `tests/integration/test_todo_subagent.py` — ~4 tests (already async)
11. `tests/observability/test_observer.py` — ~10 tests
12. `tests/plugins/test_plugin_integration.py` — ~3 tests (already async)

- [ ] **Step 3: Run all 12 test files**

```bash
python -m pytest tests/agents/ tests/core/test_agent.py tests/integration/ tests/observability/test_observer.py tests/plugins/test_plugin_integration.py -v --tb=short
```

Expected: all pass. Fix any test that fails because of missing `@pytest.mark.asyncio` decorator.

- [ ] **Step 4: Run full suite**

```bash
python -m pytest tests/ -q --tb=line
```

Expected: same 9 pre-existing failures; 0 new failures.

- [ ] **Step 5: Commit**

```bash
git add tests/conftest.py tests/agents/test_subagent.py tests/agents/test_subagent_profile.py tests/core/test_agent.py tests/integration/test_agent_profile.py tests/integration/test_context_pipeline.py tests/integration/test_llm_hooks.py tests/integration/test_loop_policy.py tests/integration/test_memory_lifecycle.py tests/integration/test_scenarios.py tests/integration/test_todo_subagent.py tests/observability/test_observer.py tests/plugins/test_plugin_integration.py
git commit -m "refactor: migrate test agent fixture to async factory"
```

---

### Task 4: Full regression verification

**Files:**
- None (verification only).

- [ ] **Step 1: Run full suite**

```bash
python -m pytest tests/ -q --tb=line
```

Expected: same 9 pre-existing failures; 0 new failures.

- [ ] **Step 2: Run CLI smoke test**

```bash
python -m pytest tests/cli/test_cli_help.py -v --tb=short
```

Expected: 3 passed.

- [ ] **Step 3: Verify merco CLI boots**

```bash
python -c "from cli.main import app; from typer.testing import CliRunner; r = CliRunner().invoke(app, ['run', '--help']); assert r.exit_code == 0; print('OK')"
```

Expected: OK.

- [ ] **Step 4: Commit verification**

```bash
git commit -m "test: verify full regression after tech debt cleanup" --allow-empty
```

(Only if no fixes were needed. If fixes were needed, commit those first.)

---

## Plan Self-Review

Spec coverage:
- Delete `_defer_plugin_init`: Task 1.
- Delete legacy Observer/restore_context/fire-and-forget from __init__: Task 1.
- CLI async + Agent.create(): Task 2.
- test_agent async fixture: Task 3.
- All consumer tests adapted: Task 3.
- Full regression: Task 4.

Placeholder scan:
- No TBD/TODO placeholders.
- File lists are exact for each task.
- The test adaptation is mechanical (add decorator + async) and doesn't change logic.

Type consistency:
- `Agent.create(config, tool_registry)` consistent across all tasks.
- `pytest.fixture` → `async def` consistent.
