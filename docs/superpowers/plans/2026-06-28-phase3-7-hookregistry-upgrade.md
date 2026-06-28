# Phase 3.7 HookRegistry Upgrade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade merco's HookRegistry from fire-and-forget events to backward-compatible interceptable hooks, then add LLM request/response interception points.

**Architecture:** Add a small `HookResult` dataclass to `merco/hooks/registry.py` and make `HookRegistry.emit()` merge structured handler returns while preserving existing None-return handler behavior. Agent consumes `HookResult` only at the two new LLM hook points: `llm.before_chat` and `llm.after_chat`.

**Tech Stack:** Python 3.11+, pytest, pytest-asyncio, existing merco Agent/HookRegistry test fixtures.

## Global Constraints

- TDD is mandatory: write each failing test first, run it and confirm the expected failure, then implement minimal production code.
- Preserve backward compatibility: existing hook handlers that return None must continue to work unchanged.
- Hook handler errors must be isolated: one failing handler must not prevent later handlers from running.
- `HookResult.stop` stops the hook handler chain only; business-flow short-circuiting is the caller's responsibility.
- `HookResult.data` is a kwargs update dict; for `llm.after_chat(response=response)`, handlers return `HookResult(data={"response": new_response})`.
- Do not begin 3.1-3.6 plugin migration in this plan; this plan only implements 3.7.

---

## File Structure

- `merco/hooks/registry.py`
  - Owns `HookResult` and `HookRegistry`.
  - Add logging and inspect-based awaitable handling.
  - Keep `on`, `off`, and `clear` behavior compatible.

- `merco/hooks/__init__.py`
  - Public exports for hook package.
  - Export `HookResult` alongside `HookRegistry`.

- `merco/core/agent.py`
  - Add `llm.before_chat` emission immediately before `self._provider.get_response(...)`.
  - Add `llm.after_chat` emission immediately after response retrieval and before usage/token processing.
  - Keep existing `llm.chat` observability event unchanged.

- `tests/hooks/test_registry.py`
  - New hook registry unit tests.
  - Focus on pure HookRegistry behavior independent of Agent.

- `tests/integration/test_llm_hooks.py`
  - New Agent integration tests for LLM request/response interception.
  - Use existing `test_agent` fixture from `tests/conftest.py`.

---

### Task 1: Add HookResult core behavior to HookRegistry

**Files:**
- Create: `tests/hooks/test_registry.py`
- Modify: `merco/hooks/registry.py`
- Modify: `merco/hooks/__init__.py`

**Interfaces:**
- Consumes: existing `HookRegistry.on(event: str, handler: Callable)`, `HookRegistry.emit(event: str, **kwargs)`.
- Produces:
  - `HookResult(data: dict | None = None, stop: bool = False)` exported from `merco.hooks` and `merco.hooks.registry`.
  - `HookRegistry.emit(event: str, **kwargs) -> HookResult | None`.

- [ ] **Step 1: Write failing tests for HookResult data, stop, backward compatibility, error isolation, and awaitable callables**

Create `tests/hooks/test_registry.py` with this full content:

```python
"""HookRegistry interception behavior tests."""

import pytest

from merco.hooks import HookRegistry, HookResult


@pytest.mark.asyncio
async def test_hook_result_data_visible_to_later_handlers():
    """HookResult.data updates kwargs for later handlers and final result."""
    hooks = HookRegistry()
    seen = []

    def first(value: str):
        seen.append(("first", value))
        return HookResult(data={"value": "changed"})

    def second(value: str):
        seen.append(("second", value))

    hooks.on("example", first)
    hooks.on("example", second)

    result = await hooks.emit("example", value="original")

    assert seen == [("first", "original"), ("second", "changed")]
    assert isinstance(result, HookResult)
    assert result.stop is False
    assert result.data == {"value": "changed"}


@pytest.mark.asyncio
async def test_hook_result_stop_stops_later_handlers():
    """HookResult(stop=True) stops the remaining handler chain."""
    hooks = HookRegistry()
    called = []

    def first(value: str):
        called.append("first")
        return HookResult(data={"value": "stopped"}, stop=True)

    def second(value: str):
        called.append("second")

    hooks.on("example", first)
    hooks.on("example", second)

    result = await hooks.emit("example", value="original")

    assert called == ["first"]
    assert isinstance(result, HookResult)
    assert result.stop is True
    assert result.data == {"value": "stopped"}


@pytest.mark.asyncio
async def test_emit_returns_none_for_no_handlers_or_no_changes():
    """emit returns None when nothing changed."""
    hooks = HookRegistry()

    no_handler_result = await hooks.emit("missing", value="original")
    assert no_handler_result is None

    called = []

    def observer(value: str):
        called.append(value)

    hooks.on("example", observer)
    observer_result = await hooks.emit("example", value="original")

    assert called == ["original"]
    assert observer_result is None


@pytest.mark.asyncio
async def test_hook_result_backward_compatible_none_handlers():
    """Existing None-return handlers still run in registration order."""
    hooks = HookRegistry()
    called = []

    def first(**kwargs):
        called.append(("first", kwargs["value"]))

    async def second(**kwargs):
        called.append(("second", kwargs["value"]))

    hooks.on("example", first)
    hooks.on("example", second)

    result = await hooks.emit("example", value="unchanged")

    assert called == [("first", "unchanged"), ("second", "unchanged")]
    assert result is None


@pytest.mark.asyncio
async def test_emit_handler_error_isolated():
    """A failing handler does not prevent later handlers from running."""
    hooks = HookRegistry()
    called = []

    def failing(**kwargs):
        called.append("failing")
        raise RuntimeError("boom")

    def working(value: str):
        called.append(("working", value))
        return HookResult(data={"value": "recovered"})

    hooks.on("example", failing)
    hooks.on("example", working)

    result = await hooks.emit("example", value="original")

    assert called == ["failing", ("working", "original")]
    assert isinstance(result, HookResult)
    assert result.data == {"value": "recovered"}


@pytest.mark.asyncio
async def test_emit_awaits_callable_returning_coroutine():
    """Callable objects returning coroutine objects are awaited."""
    hooks = HookRegistry()

    class CallableHandler:
        def __call__(self, value: str):
            async def inner():
                return HookResult(data={"value": f"{value}-awaited"})

            return inner()

    hooks.on("example", CallableHandler())

    result = await hooks.emit("example", value="original")

    assert isinstance(result, HookResult)
    assert result.data == {"value": "original-awaited"}
```

- [ ] **Step 2: Run hook registry tests to verify they fail for missing HookResult**

Run:

```bash
python -m pytest tests/hooks/test_registry.py -v --tb=short
```

Expected: FAIL during import with an error equivalent to:

```text
ImportError: cannot import name 'HookResult' from 'merco.hooks'
```

If it fails because `tests/hooks/` has no `__init__.py`, that is acceptable; pytest can still collect it. Do not add an `__init__.py` unless pytest collection fails specifically because of package discovery.

- [ ] **Step 3: Implement HookResult and upgraded emit**

Replace `merco/hooks/registry.py` with:

```python
"""钩子注册与调度"""

from __future__ import annotations

import asyncio
import inspect
import logging
from dataclasses import dataclass
from typing import Callable

logger = logging.getLogger("merco.hooks.registry")


@dataclass
class HookResult:
    """Hook handler 的结构化返回值。

    data 合并进当前事件 kwargs，后续 handler 会看到更新后的 kwargs。
    stop=True 停止后续 hook handler；业务流程是否短路由调用方决定。
    """

    data: dict | None = None
    stop: bool = False


class HookRegistry:
    """事件钩子注册表"""

    def __init__(self):
        self._hooks: dict[str, list[Callable]] = {}

    def on(self, event: str, handler: Callable):
        """注册钩子处理器"""
        if event not in self._hooks:
            self._hooks[event] = []
        self._hooks[event].append(handler)

    def off(self, event: str, handler: Callable):
        """移除钩子处理器"""
        if event in self._hooks:
            self._hooks[event].remove(handler)

    async def emit(self, event: str, **kwargs) -> HookResult | None:
        """触发事件。

        默认 fire-and-forget：handler 返回 None 时不影响流程。
        handler 可返回 HookResult(data=...) 修改后续 handler 看到的 kwargs。
        handler 可返回 HookResult(stop=True) 停止后续 handler 链。
        """
        handlers = self._hooks.get(event, [])
        current = dict(kwargs)
        changed = False

        for handler in handlers:
            try:
                result = handler(**current)
                if inspect.isawaitable(result):
                    result = await result
            except Exception:
                logger.debug("hook %s handler error", event, exc_info=True)
                continue

            if isinstance(result, HookResult):
                if result.data:
                    current.update(result.data)
                    changed = True
                if result.stop:
                    return HookResult(data=current, stop=True)

        if changed:
            return HookResult(data=current, stop=False)
        return None

    def clear(self, event: str = None):
        """清除钩子"""
        if event:
            self._hooks.pop(event, None)
        else:
            self._hooks.clear()
```

Update `merco/hooks/__init__.py` to:

```python
"""钩子系统"""

from .registry import HookRegistry, HookResult

__all__ = ["HookRegistry", "HookResult"]
```

- [ ] **Step 4: Run hook registry tests to verify they pass**

Run:

```bash
python -m pytest tests/hooks/test_registry.py -v --tb=short
```

Expected: all 6 tests PASS.

- [ ] **Step 5: Run existing plugin tests to verify compatibility with current hooks**

Run:

```bash
python -m pytest tests/plugins/ -v --tb=short
```

Expected: all existing plugin tests PASS.

- [ ] **Step 6: Commit Task 1**

```bash
git add merco/hooks/registry.py merco/hooks/__init__.py tests/hooks/test_registry.py
git commit -m "feat: add interceptable hook results"
```

---

### Task 2: Add llm.before_chat request interception to Agent

**Files:**
- Create/Modify: `tests/integration/test_llm_hooks.py`
- Modify: `merco/core/agent.py`

**Interfaces:**
- Consumes: `HookResult(data={"messages": new_messages, "tools": new_tools})` from Task 1.
- Produces: `Agent._agent_loop()` emits `llm.before_chat` before provider invocation and consumes `messages`, `tools`, and optional `response` from returned `HookResult.data`.

- [ ] **Step 1: Write failing integration tests for before_chat modifying messages/tools and short-circuiting response**

Create `tests/integration/test_llm_hooks.py` with this content:

```python
"""Integration tests for interceptable LLM hooks."""

import pytest

from merco.hooks import HookResult


@pytest.mark.asyncio
async def test_llm_before_chat_can_modify_messages_and_tools(test_agent):
    """llm.before_chat can replace messages and tools before LLM call."""
    agent = test_agent
    agent.llm.responses = [{"content": "done", "finish_reason": "stop"}]

    async def before_chat(messages, tools, **kwargs):
        modified_messages = list(messages)
        modified_messages.append({"role": "user", "content": "hook injected"})
        return HookResult(data={"messages": modified_messages, "tools": []})

    agent.hooks.on("llm.before_chat", before_chat)

    result = await agent.run("hello")

    assert result == "done"
    assert agent.llm.calls, "LLM should have been called"
    call = agent.llm.calls[-1]
    assert call["messages"][-1] == {"role": "user", "content": "hook injected"}
    assert call["tools"] is None


@pytest.mark.asyncio
async def test_llm_before_chat_can_short_circuit_with_response(test_agent):
    """llm.before_chat stop=True with response skips the LLM call."""
    agent = test_agent
    agent.llm.responses = [{"content": "should not be used", "finish_reason": "stop"}]

    async def before_chat(messages, tools, **kwargs):
        return HookResult(
            data={"response": {"content": "from hook", "finish_reason": "stop"}},
            stop=True,
        )

    agent.hooks.on("llm.before_chat", before_chat)

    result = await agent.run("hello")

    assert result == "from hook"
    assert agent.llm.calls == []
```

- [ ] **Step 2: Run before_chat integration tests to verify they fail**

Run:

```bash
python -m pytest tests/integration/test_llm_hooks.py::test_llm_before_chat_can_modify_messages_and_tools tests/integration/test_llm_hooks.py::test_llm_before_chat_can_short_circuit_with_response -v --tb=short
```

Expected:
- First test FAILS because `llm.before_chat` is not emitted, so LLM call messages do not include `hook injected` and tools are not changed to `None`.
- Second test FAILS because LLM is still called and returns `should not be used`.

- [ ] **Step 3: Implement before_chat emission in Agent._agent_loop**

In `merco/core/agent.py`, inside `_agent_loop()`, locate this block:

```python
try:
    response = await self._provider.get_response(
        self, messages, tools or None)
except Exception as e:
```

Replace it with:

```python
try:
    before = await self.hooks.emit("llm.before_chat", messages=messages, tools=tools)
    if before and before.data:
        messages = before.data.get("messages", messages)
        tools = before.data.get("tools", tools)
        if before.stop:
            response = before.data["response"]
        else:
            response = await self._provider.get_response(
                self, messages, tools or None)
    else:
        response = await self._provider.get_response(
            self, messages, tools or None)
except Exception as e:
```

Do not change the existing exception recovery block after `except Exception as e:`.

- [ ] **Step 4: Run before_chat integration tests to verify they pass**

Run:

```bash
python -m pytest tests/integration/test_llm_hooks.py::test_llm_before_chat_can_modify_messages_and_tools tests/integration/test_llm_hooks.py::test_llm_before_chat_can_short_circuit_with_response -v --tb=short
```

Expected: both tests PASS.

- [ ] **Step 5: Run agent loop smoke tests**

Run:

```bash
python -m pytest tests/integration/test_agent_loop.py tests/core/test_agent.py -v --tb=short
```

Expected: all selected tests PASS.

- [ ] **Step 6: Commit Task 2**

```bash
git add merco/core/agent.py tests/integration/test_llm_hooks.py
git commit -m "feat: add llm before chat hook"
```

---

### Task 3: Add llm.after_chat response interception to Agent

**Files:**
- Modify: `tests/integration/test_llm_hooks.py`
- Modify: `merco/core/agent.py`

**Interfaces:**
- Consumes: `HookResult(data={"response": new_response})` from Task 1.
- Produces: `Agent._agent_loop()` emits `llm.after_chat` after response retrieval and uses updated `response` for all existing loop logic.

- [ ] **Step 1: Add failing after_chat integration test**

Append this test to `tests/integration/test_llm_hooks.py`:

```python

@pytest.mark.asyncio
async def test_llm_after_chat_can_replace_response(test_agent):
    """llm.after_chat can replace the LLM response before Agent processes it."""
    agent = test_agent
    agent.llm.responses = [{"content": "original", "finish_reason": "stop"}]

    async def after_chat(response, **kwargs):
        assert response["content"] == "original"
        return HookResult(
            data={"response": {"content": "modified", "finish_reason": "stop"}}
        )

    agent.hooks.on("llm.after_chat", after_chat)

    result = await agent.run("hello")

    assert result == "modified"
    assert agent.session.messages[-1]["content"] == "modified"
```

- [ ] **Step 2: Run after_chat test to verify it fails**

Run:

```bash
python -m pytest tests/integration/test_llm_hooks.py::test_llm_after_chat_can_replace_response -v --tb=short
```

Expected: FAIL because `llm.after_chat` is not emitted and result remains `original`.

- [ ] **Step 3: Implement after_chat emission in Agent._agent_loop**

In `merco/core/agent.py`, immediately after the before_chat/provider response retrieval block and before this existing comment:

```python
# 记录 API 返回的实测 token（流式可能无 usage，fallback 到估算值）
```

Add:

```python
after = await self.hooks.emit("llm.after_chat", response=response)
if after and after.data:
    response = after.data.get("response", response)
```

The resulting structure should be:

```python
try:
    before = await self.hooks.emit("llm.before_chat", messages=messages, tools=tools)
    if before and before.data:
        messages = before.data.get("messages", messages)
        tools = before.data.get("tools", tools)
        if before.stop:
            response = before.data["response"]
        else:
            response = await self._provider.get_response(
                self, messages, tools or None)
    else:
        response = await self._provider.get_response(
            self, messages, tools or None)
except Exception as e:
    ... existing recovery block unchanged ...

after = await self.hooks.emit("llm.after_chat", response=response)
if after and after.data:
    response = after.data.get("response", response)

# 记录 API 返回的实测 token（流式可能无 usage，fallback 到估算值）
```

- [ ] **Step 4: Run after_chat test to verify it passes**

Run:

```bash
python -m pytest tests/integration/test_llm_hooks.py::test_llm_after_chat_can_replace_response -v --tb=short
```

Expected: PASS.

- [ ] **Step 5: Run all LLM hook integration tests**

Run:

```bash
python -m pytest tests/integration/test_llm_hooks.py -v --tb=short
```

Expected: all 3 tests PASS.

- [ ] **Step 6: Commit Task 3**

```bash
git add merco/core/agent.py tests/integration/test_llm_hooks.py
git commit -m "feat: add llm after chat hook"
```

---

### Task 4: Full regression verification and documentation check

**Files:**
- Modify: none unless verification exposes a problem.

**Interfaces:**
- Consumes: Tasks 1-3 completed.
- Produces: verified 3.7 implementation with tests passing.

- [ ] **Step 1: Run focused hook and plugin tests**

Run:

```bash
python -m pytest tests/hooks/test_registry.py tests/integration/test_llm_hooks.py tests/plugins/ -v --tb=short
```

Expected: all selected tests PASS.

- [ ] **Step 2: Run full test suite**

Run:

```bash
python -m pytest tests/ -v --tb=short
```

Expected: all tests PASS or only known pre-existing failures. If failures occur, inspect whether they are caused by this change. Fix caused failures with a new RED/GREEN cycle before continuing.

- [ ] **Step 3: Inspect final diff**

Run:

```bash
git diff -- merco/hooks/registry.py merco/hooks/__init__.py merco/core/agent.py tests/hooks/test_registry.py tests/integration/test_llm_hooks.py
```

Expected:
- `HookResult` exists in `merco/hooks/registry.py`.
- `HookResult` is exported from `merco/hooks/__init__.py`.
- `llm.before_chat` and `llm.after_chat` are emitted in `Agent._agent_loop()`.
- Tests cover HookResult data, stop, backward compatibility, error isolation, awaitable callables, before_chat modification, before_chat short-circuit, and after_chat response replacement.

- [ ] **Step 4: Commit verification-only changes if any were needed**

If Step 2 required fixes, commit them:

```bash
git add merco/hooks/registry.py merco/hooks/__init__.py merco/core/agent.py tests/hooks/test_registry.py tests/integration/test_llm_hooks.py
git commit -m "test: verify hook interception regression coverage"
```

If no fixes were needed, do not create an empty commit.

---

## Plan Self-Review

Spec coverage:
- HookResult dataclass: Task 1.
- data merge visible to later handlers: Task 1.
- data-only emit return: Task 1.
- stop stops handler chain only: Task 1 tests registry behavior; Task 2 defines business short-circuit only for before_chat.
- handler error isolation: Task 1.
- inspect.isawaitable support: Task 1.
- llm.before_chat modifies messages/tools: Task 2.
- llm.before_chat short-circuits with response: Task 2.
- llm.after_chat replaces response: Task 3.
- No 3.1-3.6 plugin migration: explicitly constrained out of scope.

Placeholder scan:
- No TBD/TODO/fill-in steps.
- Every code-changing step includes exact code.
- Every test step includes exact command and expected result.

Type consistency:
- `HookResult(data: dict | None = None, stop: bool = False)` used consistently.
- `emit(...) -> HookResult | None` used consistently.
- LLM hook data keys are consistently `messages`, `tools`, and `response`.
