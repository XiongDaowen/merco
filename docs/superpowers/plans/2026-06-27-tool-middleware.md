# merco ToolRegistry Middleware Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 ToolRegistry 安全守卫和错误处理从硬编码改为可组合的 ToolMiddleware 链

**Architecture:** ToolContext 贯穿 before/during/after，ToolMiddlewareChain 洋葱模型执行，ToolRegistry 只负责路由

**Tech Stack:** Python 3.12, ABC, dataclass, pytest

---

## 文件结构

| 文件 | 职责 |
|------|------|
| `merco/tools/middleware.py` | ToolContext, ToolMiddleware, ToolMiddlewareChain, GuardMiddleware, ErrorHandlingMiddleware |
| `merco/tools/registry.py` | ToolRegistry 增加 `_middleware` 字段和 `use(mw)` 方法，execute 委托给 chain |
| `merco/core/agent.py` | 在 ToolRegistry 装配时挂 Guard + ErrorHandling middleware |
| `tests/tools/test_middleware.py` | 单元测试 |
| `tests/integration/test_tool_middleware.py` | 集成测试（行为等价旧版） |

---

## Task 1: ToolContext + ToolMiddleware + Chain

**Files:**
- Create: `merco/tools/middleware.py`
- Test: `tests/tools/test_middleware.py`

- [ ] **Step 1: Write failing tests**

Create `tests/tools/test_middleware.py`:

```python
"""ToolMiddleware + Chain 单测"""
import pytest
from merco.tools.middleware import ToolContext, ToolMiddleware, ToolMiddlewareChain


class StubTool:
    name = "stub"
    description = "stub"
    parameters = {}
    toolset = "test"

    async def execute(self, **kwargs):
        return {"echo": kwargs}


def test_tool_context_default():
    """ToolContext 默认值"""
    ctx = ToolContext(tool_name="t", arguments={"a": 1})
    assert ctx.tool is None
    assert ctx.result is None
    assert ctx.error is None
    assert ctx.metadata == {}


def test_middleware_abc():
    """ToolMiddleware 不能直接实例化"""
    with pytest.raises(TypeError):
        ToolMiddleware()  # noqa


class PassMiddleware(ToolMiddleware):
    name = "pass"

    async def before(self, ctx):
        return None

    async def after(self, ctx):
        return None

    async def on_error(self, ctx):
        return None


async def test_chain_empty_executes_tool():
    """空 chain 直接调工具"""
    chain = ToolMiddlewareChain()
    ctx = ToolContext(tool_name="t", arguments={"x": 1}, tool=StubTool())
    result = await chain.execute(ctx, lambda: StubTool().execute(**ctx.arguments))
    assert result == {"echo": {"x": 1}}


class ShortCircuitMiddleware(ToolMiddleware):
    name = "short"
    async def before(self, ctx):
        return {"short_circuit": True}


async def test_chain_before_short_circuit():
    """before 返回 dict 短路"""
    chain = ToolMiddlewareChain()
    chain.use(ShortCircuitMiddleware())
    called = []

    async def call_tool():
        called.append(True)
        return {"ok": True}

    ctx = ToolContext(tool_name="t", arguments={})
    result = await chain.execute(ctx, call_tool)
    assert result == {"short_circuit": True}
    assert called == []


class OrderRecorder(ToolMiddleware):
    def __init__(self, name):
        self.name = name
        self.events = []

    async def before(self, ctx):
        self.events.append(f"{self.name}:before")

    async def after(self, ctx):
        self.events.append(f"{self.name}:after")

    async def on_error(self, ctx):
        self.events.append(f"{self.name}:on_error")


async def test_chain_order_onion():
    """洋葱模型：before 正序，after 逆序"""
    chain = ToolMiddlewareChain()
    a = OrderRecorder("a")
    b = OrderRecorder("b")
    chain.use(a)
    chain.use(b)

    ctx = ToolContext(tool_name="t", arguments={}, tool=StubTool())
    await chain.execute(ctx, lambda: StubTool().execute())

    assert a.events == ["a:before", "b:before", "b:after", "a:after"]


async def test_chain_on_error_invokes_in_reverse():
    """on_error 逆序执行"""
    chain = ToolMiddlewareChain()
    a = OrderRecorder("a")
    b = OrderRecorder("b")
    chain.use(a)
    chain.use(b)

    async def fail():
        raise RuntimeError("boom")

    ctx = ToolContext(tool_name="t", arguments={}, tool=StubTool())
    with pytest.raises(RuntimeError):
        await chain.execute(ctx, fail)

    assert a.events == ["a:before", "b:before", "b:on_error", "a:on_error"]


class ErrorOverrideMiddleware(ToolMiddleware):
    name = "error_override"

    async def on_error(self, ctx):
        return {"error": str(ctx.error), "recovered": True}


async def test_chain_on_error_can_short_circuit():
    """on_error 返回 dict → 短路"""
    chain = ToolMiddlewareChain()
    chain.use(ErrorOverrideMiddleware())

    async def fail():
        raise ValueError("nope")

    ctx = ToolContext(tool_name="t", arguments={}, tool=StubTool())
    result = await chain.execute(ctx, fail)
    assert result == {"error": "nope", "recovered": True}


async def test_chain_after_can_replace_result():
    """after 返回 dict → 替换 result"""
    chain = ToolMiddlewareChain()

    class ReplaceAfter(ToolMiddleware):
        name = "replace"
        async def after(self, ctx):
            return {"replaced": True}

    chain.use(ReplaceAfter())
    ctx = ToolContext(tool_name="t", arguments={}, tool=StubTool())
    result = await chain.execute(ctx, lambda: {"original": True})
    assert result == {"replaced": True}


async def test_chain_before_returns_context_continues():
    """before 返回 ctx → 继续"""
    chain = ToolMiddlewareChain()

    class Mutator(ToolMiddleware):
        name = "mutate"
        async def before(self, ctx):
            ctx.metadata["x"] = 1
            return ctx

    chain.use(Mutator())
    ctx = ToolContext(tool_name="t", arguments={}, tool=StubTool())
    await chain.execute(ctx, lambda: {})
    assert ctx.metadata["x"] == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/xiowen/code/merco && python3 -m pytest tests/tools/test_middleware.py -v`
Expected: ImportError

- [ ] **Step 3: Implement middleware.py**

Create `merco/tools/middleware.py`:

```python
"""ToolContext + ToolMiddleware + ToolMiddlewareChain"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ToolContext:
    """工具执行上下文，贯穿 before/during/after"""
    tool_name: str
    arguments: dict
    tool: object | None = None
    result: dict | None = None
    error: BaseException | None = None
    metadata: dict = field(default_factory=dict)


class ToolMiddleware(ABC):
    """工具中间件基类"""
    name: str = ""

    @abstractmethod
    async def before(self, ctx: ToolContext):
        """执行前。返回 dict 短路；返回 ctx/None 继续"""
        ...

    @abstractmethod
    async def after(self, ctx: ToolContext):
        """执行后。可修改 ctx.result；返回 dict 替换 result"""
        ...

    @abstractmethod
    async def on_error(self, ctx: ToolContext):
        """异常处理。返回 dict → 错误结果；None → 抛"""
        ...


class ToolMiddlewareChain:
    """洋葱模型：before 正序，after/on_error 逆序"""

    def __init__(self):
        self._middlewares: list[ToolMiddleware] = []

    def use(self, middleware: ToolMiddleware) -> "ToolMiddlewareChain":
        self._middlewares.append(middleware)
        return self

    async def execute(self, ctx: ToolContext, call_tool) -> dict:
        for mw in self._middlewares:
            r = await mw.before(ctx)
            if isinstance(r, dict):
                return r
            if isinstance(r, ToolContext):
                ctx = r

        try:
            ctx.result = await call_tool()
        except BaseException as e:
            ctx.error = e
            for mw in reversed(self._middlewares):
                r = await mw.on_error(ctx)
                if isinstance(r, dict):
                    return r
            raise

        for mw in reversed(self._middlewares):
            r = await mw.after(ctx)
            if isinstance(r, dict):
                ctx.result = r
            elif isinstance(r, ToolContext):
                ctx = r
        return ctx.result
```

- [ ] **Step 4: Run tests**

Run: `cd /home/xiowen/code/merco && python3 -m pytest tests/tools/test_middleware.py -v`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
cd /home/xiowen/code/merco
git add merco/tools/middleware.py tests/tools/test_middleware.py
git commit -m "feat: add ToolMiddleware chain and ToolContext"
```

---

## Task 2: GuardMiddleware + ErrorHandlingMiddleware

**Files:**
- Modify: `merco/tools/middleware.py`
- Test: `tests/tools/test_middleware.py`

- [ ] **Step 1: Append test**

Append to `tests/tools/test_middleware.py`:

```python

from merco.tools.middleware import GuardMiddleware, ErrorHandlingMiddleware
from merco.sandbox.guard import GuardAction, GuardResult, GuardConfirmationRequired


class StubGuard:
    def __init__(self, result):
        self._result = result
        self.called = []

    async def check(self, tool_name, arguments):
        self.called.append((tool_name, arguments))
        return self._result


@pytest.mark.asyncio
async def test_guard_middleware_deny_returns_error():
    """GuardMiddleware DENY → 返回错误 dict"""
    guard = StubGuard(GuardResult(action=GuardAction.DENY, command="", reason="blocked"))
    mw = GuardMiddleware(guard)
    ctx = ToolContext(tool_name="bash", arguments={"command": "rm"})
    result = await mw.before(ctx)
    assert result == {"error": "操作被安全守卫拒绝: blocked", "tool": "bash"}


@pytest.mark.asyncio
async def test_guard_middleware_ask_raises():
    """GuardMiddleware ASK → raise GuardConfirmationRequired"""
    guard = StubGuard(GuardResult(action=GuardAction.ASK, command="", reason="need confirm"))
    mw = GuardMiddleware(guard)
    ctx = ToolContext(tool_name="bash", arguments={})
    with pytest.raises(GuardConfirmationRequired):
        await mw.before(ctx)


@pytest.mark.asyncio
async def test_guard_middleware_allow_continues():
    """GuardMiddleware ALLOW → None 继续"""
    guard = StubGuard(GuardResult(action=GuardAction.ALLOW, command=""))
    mw = GuardMiddleware(guard)
    ctx = ToolContext(tool_name="bash", arguments={})
    assert await mw.before(ctx) is None


@pytest.mark.asyncio
async def test_error_handling_returns_tool_error():
    """ErrorHandlingMiddleware on_error 返回结构化结果"""
    mw = ErrorHandlingMiddleware()
    from unittest.mock import MagicMock
    tool = MagicMock()
    tool.parameters = {"type": "object"}
    ctx = ToolContext(tool_name="bash", arguments={"cmd": "x"}, tool=tool, error=RuntimeError("boom"))
    result = await mw.on_error(ctx)
    assert "error" in result
    assert result["tool"] == "bash"
```

- [ ] **Step 2: Run tests**

Run: `cd /home/xiowen/code/merco && python3 -m pytest tests/tools/test_middleware.py -v`
Expected: ImportError

- [ ] **Step 3: Add GuardMiddleware + ErrorHandlingMiddleware**

Append to `merco/tools/middleware.py`:

```python


class GuardMiddleware(ToolMiddleware):
    """包装 ToolGuard — DENY 返回错误，ASK 抛异常，ALLOW 继续"""
    name = "guard"

    def __init__(self, guard):
        self.guard = guard

    async def before(self, ctx: ToolContext):
        result = await self.guard.check(ctx.tool_name, ctx.arguments)
        if result.action == GuardAction.DENY:
            return {"error": f"操作被安全守卫拒绝: {result.reason}", "tool": ctx.tool_name}
        if result.action == GuardAction.ASK:
            from merco.sandbox.guard import GuardConfirmationRequired
            raise GuardConfirmationRequired(result)
        return None


class ErrorHandlingMiddleware(ToolMiddleware):
    """工具异常 → 结构化 tool_error 结果"""
    name = "error_handling"

    async def on_error(self, ctx: ToolContext):
        from merco.core.self_healing import tool_error
        return tool_error(
            ctx.error,
            ctx.tool_name,
            getattr(ctx.tool, 'parameters', None) if ctx.tool else None,
        )
```

Add import to top:

```python
from merco.sandbox.guard import GuardAction
```

- [ ] **Step 4: Run tests**

Run: `cd /home/xiowen/code/merco && python3 -m pytest tests/tools/test_middleware.py -v`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
cd /home/xiowen/code/merco
git add merco/tools/middleware.py tests/tools/test_middleware.py
git commit -m "feat: add GuardMiddleware and ErrorHandlingMiddleware"
```

---

## Task 3: ToolRegistry 改造为路由

**Files:**
- Modify: `merco/tools/registry.py`

- [ ] **Step 1: Rewrite ToolRegistry.execute to use middleware chain**

In `merco/tools/registry.py`:

1. Add at top:

```python
from merco.tools.middleware import ToolContext, ToolMiddlewareChain
```

2. Add `use()` method and `_middleware` field:

```python
    def __init__(self):
        self._tools: dict[str, BaseTool] = {}
        self._enabled_toolsets: set | None = None
        self._middleware = ToolMiddlewareChain()

    def use(self, middleware) -> "ToolRegistry":
        """挂载中间件"""
        self._middleware.use(middleware)
        return self
```

3. Replace the existing `execute` body (everything after `tool = self.get(tool_name)`) with:

```python
    async def execute(self, tool_name: str, **kwargs) -> dict:
        """执行指定工具。中间件链处理安全检查和错误处理。"""
        tool = self.get(tool_name)
        if tool is None:
            return {"error": f"工具 '{tool_name}' 不存在"}

        ctx = ToolContext(tool_name=tool_name, arguments=kwargs, tool=tool)
        return await self._middleware.execute(ctx, lambda: tool.execute(**kwargs))
```

4. Remove the now-unused `from merco.sandbox.guard import GuardAction` (no longer used here).

- [ ] **Step 2: Run guard + tool tests**

Run:

```bash
cd /home/xiowen/code/merco
python3 -m pytest tests/tools/ tests/test_registry_guard.py -v 2>&1 | tail -15
```

Expected: existing tests pass because Agent wires GuardMiddleware + ErrorHandlingMiddleware in Task 4.

If Agent wiring isn't done yet, run only:

```bash
cd /home/xiowen/code/merco
python3 -m pytest tests/tools/test_middleware.py -v
```

- [ ] **Step 3: Commit**

```bash
cd /home/xiowen/code/merco
git add merco/tools/registry.py
git commit -m "refactor: ToolRegistry delegates execute to middleware chain"
```

---

## Task 4: Agent 装配 Guard + ErrorHandling middleware

**Files:**
- Modify: `merco/core/agent.py`

- [ ] **Step 1: Wire middlewares in Agent.__init__**

In `merco/core/agent.py`, right after `self.guard = ToolGuard(...)` (around line 339):

```python
        from merco.tools.middleware import GuardMiddleware, ErrorHandlingMiddleware
        self.tool_registry.use(GuardMiddleware(self.guard))
        self.tool_registry.use(ErrorHandlingMiddleware())
```

- [ ] **Step 2: Run full integration + guard tests**

Run:

```bash
cd /home/xiowen/code/merco
python3 -m pytest tests/integration/test_scenarios.py tests/test_guard.py tests/tools/ -v 2>&1 | tail -20
```

Expected: existing guard / tool-call tests all pass

- [ ] **Step 3: Commit**

```bash
cd /home/xiowen/code/merco
git add merco/core/agent.py
git commit -m "feat: Agent wires Guard + ErrorHandling middleware at startup"
```

---

## Task 5: 集成测试

**Files:**
- Create: `tests/integration/test_tool_middleware.py`

- [ ] **Step 1: Write integration test**

Create `tests/integration/test_tool_middleware.py`:

```python
"""ToolMiddleware 集成测试"""
import pytest
from merco.tools.middleware import ToolMiddleware, ToolContext
from merco.tools.registry import ToolRegistry
from merco.tools.base import BaseTool


class RecordArgsTool(BaseTool):
    name = "record"
    description = "rec"
    parameters = {"type": "object", "properties": {}}
    toolset = "test"

    def __init__(self):
        self.calls = []

    async def execute(self, **kwargs):
        self.calls.append(kwargs)
        return {"ok": True}


@pytest.mark.asyncio
async def test_registry_runs_tool_with_no_middleware():
    """无中间件时直接执行"""
    reg = ToolRegistry()
    tool = RecordArgsTool()
    reg.register(tool)
    result = await reg.execute("record", x=1)
    assert result == {"ok": True}
    assert tool.calls == [{"x": 1}]


@pytest.mark.asyncio
async def test_registry_plugin_can_inject_middleware():
    """插件可在 registry 挂中间件"""
    reg = ToolRegistry()
    tool = RecordArgsTool()
    reg.register(tool)

    seen = []

    class Trace(ToolMiddleware):
        name = "trace"
        async def before(self, ctx):
            seen.append(("before", ctx.tool_name))
        async def after(self, ctx):
            seen.append(("after", ctx.tool_name))
        async def on_error(self, ctx):
            seen.append(("error", ctx.tool_name))

    reg.use(Trace())
    await reg.execute("record", x=1)
    assert seen == [("before", "record"), ("after", "record")]


@pytest.mark.asyncio
async def test_registry_plugin_can_short_circuit():
    """插件可短路工具执行"""
    reg = ToolRegistry()
    tool = RecordArgsTool()
    reg.register(tool)

    class Deny(ToolMiddleware):
        name = "deny"
        async def before(self, ctx):
            return {"error": "blocked by plugin"}

    reg.use(Deny())
    result = await reg.execute("record", x=1)
    assert result == {"error": "blocked by plugin"}
    assert tool.calls == []  # tool not called
```

- [ ] **Step 2: Run tests**

Run: `cd /home/xiowen/code/merco && python3 -m pytest tests/integration/test_tool_middleware.py -v`
Expected: 3 passed

- [ ] **Step 3: Commit**

```bash
cd /home/xiowen/code/merco
git add tests/integration/test_tool_middleware.py
git commit -m "test: ToolRegistry middleware integration"
```

---

## Task 6: 文档更新

**Files:**
- Modify: `docs/project-vision/references/architecture-refactor-plan.md`
- Modify: `docs/project-vision/references/progress.md`

- [ ] **Step 1: Update refactor plan**

Mark Phase 2.2 as done:

```markdown
### 2.2 ToolRegistry 中间件链 ✅ 已完成
```

- [ ] **Step 2: Update progress.md**

Add ToolMiddleware entry.

- [ ] **Step 3: Commit**

```bash
cd /home/xiowen/code/merco
git add docs/project-vision/references/architecture-refactor-plan.md docs/project-vision/references/progress.md
git commit -m "docs: mark ToolRegistry middleware refactor complete"
```

---

## Self-Review

**Spec coverage:**
- ✅ ToolContext / ToolMiddleware ABC (Task 1)
- ✅ ToolMiddlewareChain 洋葱模型 (Task 1)
- ✅ GuardMiddleware + ErrorHandlingMiddleware (Task 2)
- ✅ ToolRegistry.execute 路由 (Task 3)
- ✅ Agent 装配 (Task 4)
- ✅ 集成测试 (Task 5)
- ✅ 文档 (Task 6)

**Behavior safety:** 通过 Task 4 装配 Guard + ErrorHandling，行为与旧 registry 完全等价
