# merco LoopPolicy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 Agent Loop 退出条件从硬编码改为可拔插的 LoopPolicy 策略，同时默认行为保持不变

**Architecture:** LoopState/LoopDecision 数据模型 + LoopPolicy ABC + DefaultLoopPolicy + LoopPolicyRegistry + Agent._agent_loop 调用 active policy

**Tech Stack:** Python 3.12, dataclass, ABC, pytest

---

## 文件结构

| 文件 | 职责 |
|------|------|
| `merco/core/loop_policy.py` | LoopState, LoopDecision, LoopPolicy, DefaultLoopPolicy, LoopPolicyRegistry |
| `merco/core/agent.py` | 装配 loop_policies，_agent_loop 调用策略 |
| `merco/plugins/base.py` | PluginContext 新增 loop_policies |
| `tests/core/test_loop_policy.py` | LoopPolicy 单测 |
| `tests/integration/test_loop_policy.py` | Agent 行为等价 + 自定义策略测试 |
| `docs/project-vision/references/architecture-refactor-plan.md` | Phase 2 进度更新 |

---

## Task 1: LoopPolicy 数据模型 + DefaultLoopPolicy + Registry

**Files:**
- Create: `merco/core/loop_policy.py`
- Test: `tests/core/test_loop_policy.py`

- [ ] **Step 1: Write failing tests**

Create `tests/core/test_loop_policy.py`:

```python
"""LoopPolicy 单测"""
import pytest
from merco.core.loop_policy import (
    LoopState, LoopDecision, LoopPolicy, DefaultLoopPolicy, LoopPolicyRegistry
)


class AlwaysContinuePolicy(LoopPolicy):
    name = "always_continue"

    async def decide(self, response, state):
        return LoopDecision(action="continue", reason="test")


def test_loop_state_creation():
    """LoopState 创建"""
    state = LoopState(
        iteration=1,
        tool_calls_count=2,
        max_tool_calls=10,
        has_tool_calls=True,
        finish_reason="tool_calls",
    )
    assert state.iteration == 1
    assert state.has_tool_calls is True


def test_loop_decision_creation():
    """LoopDecision 创建"""
    d = LoopDecision(action="exit", reason="done")
    assert d.action == "exit"
    assert d.reason == "done"


def test_loop_policy_abc():
    """LoopPolicy 抽象类不能直接实例化"""
    with pytest.raises(TypeError):
        LoopPolicy()  # noqa


@pytest.mark.asyncio
async def test_default_policy_continue_on_tool_calls():
    """默认策略：有 tool_calls → continue"""
    p = DefaultLoopPolicy()
    state = LoopState(0, 0, 10, has_tool_calls=True)
    d = await p.decide({"tool_calls": [{"name": "echo"}]}, state)
    assert d.action == "continue"


@pytest.mark.asyncio
async def test_default_policy_exit_without_tool_calls():
    """默认策略：无 tool_calls → exit"""
    p = DefaultLoopPolicy()
    state = LoopState(0, 0, 10, has_tool_calls=False)
    d = await p.decide({"content": "done"}, state)
    assert d.action == "exit"


def test_registry_register_get_active():
    """Registry 注册/获取/激活"""
    reg = LoopPolicyRegistry()
    default = DefaultLoopPolicy()
    custom = AlwaysContinuePolicy()
    reg.register(default)
    reg.register(custom)
    assert reg.get("default") is default
    reg.set_active("always_continue")
    assert reg.active is custom


def test_registry_set_missing_raises():
    """set_active 未注册策略抛 KeyError"""
    reg = LoopPolicyRegistry()
    reg.register(DefaultLoopPolicy())
    with pytest.raises(KeyError):
        reg.set_active("missing")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/xiowen/code/merco && python3 -m pytest tests/core/test_loop_policy.py -v`
Expected: ImportError

- [ ] **Step 3: Implement loop_policy.py**

Create `merco/core/loop_policy.py`:

```python
"""Agent LoopPolicy — 可拔插循环策略"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class LoopState:
    """Loop 当前状态"""
    iteration: int
    tool_calls_count: int
    max_tool_calls: int
    has_tool_calls: bool
    finish_reason: str | None = None


@dataclass
class LoopDecision:
    """Loop 策略决策"""
    action: str  # "continue" | "exit"
    reason: str = ""


class LoopPolicy(ABC):
    """Agent Loop 策略基类"""
    name: str = ""

    @abstractmethod
    async def decide(self, response: dict, state: LoopState) -> LoopDecision:
        """根据 LLM response 和当前 state 决定继续或退出"""
        ...


class DefaultLoopPolicy(LoopPolicy):
    """默认策略：完全复刻当前行为"""
    name = "default"

    async def decide(self, response: dict, state: LoopState) -> LoopDecision:
        if state.has_tool_calls:
            return LoopDecision(action="continue", reason="tool_calls present")
        return LoopDecision(action="exit", reason="no tool_calls")


class LoopPolicyRegistry:
    """LoopPolicy 注册表"""

    def __init__(self):
        self._policies: dict[str, LoopPolicy] = {}
        self._active: str = "default"

    def register(self, policy: LoopPolicy) -> None:
        self._policies[policy.name] = policy

    def get(self, name: str) -> LoopPolicy | None:
        return self._policies.get(name)

    def list(self) -> list[LoopPolicy]:
        return list(self._policies.values())

    def set_active(self, name: str) -> None:
        if name not in self._policies:
            raise KeyError(name)
        self._active = name

    @property
    def active(self) -> LoopPolicy:
        return self._policies[self._active]
```

- [ ] **Step 4: Run tests**

Run: `cd /home/xiowen/code/merco && python3 -m pytest tests/core/test_loop_policy.py -v`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
cd /home/xiowen/code/merco
git add merco/core/loop_policy.py tests/core/test_loop_policy.py
git commit -m "feat: add LoopPolicy primitives and registry"
```

---

## Task 2: PluginContext 暴露 loop_policies + Agent 装配

**Files:**
- Modify: `merco/plugins/base.py`
- Modify: `merco/core/agent.py`

- [ ] **Step 1: Add loop_policies to PluginContext**

In `merco/plugins/base.py`:

- Add TYPE_CHECKING import:

```python
from merco.core.loop_policy import LoopPolicyRegistry
```

- Add optional constructor param:

```python
loop_policies: "LoopPolicyRegistry" = None,
```

- Store:

```python
self.loop_policies = loop_policies
```

- [ ] **Step 2: Wire in Agent.__init__**

In `merco/core/agent.py`, before `PluginContext(...)` construction, add:

```python
        # ── Loop Policy ──
        from merco.core.loop_policy import LoopPolicyRegistry, DefaultLoopPolicy
        self.loop_policies = LoopPolicyRegistry()
        self.loop_policies.register(DefaultLoopPolicy())
        self.loop_policies.set_active("default")
```

When creating `PluginContext`, pass:

```python
loop_policies=self.loop_policies,
```

- [ ] **Step 3: Verify syntax + plugin tests**

Run:

```bash
cd /home/xiowen/code/merco
python3 -m py_compile merco/core/agent.py merco/plugins/base.py
python3 -m pytest tests/plugins/ tests/core/test_loop_policy.py -v
```

Expected: all pass

- [ ] **Step 4: Commit**

```bash
cd /home/xiowen/code/merco
git add merco/plugins/base.py merco/core/agent.py
git commit -m "feat: expose LoopPolicyRegistry through PluginContext and Agent"
```

---

## Task 3: Agent._agent_loop 调用 LoopPolicy

**Files:**
- Modify: `merco/core/agent.py`
- Test: `tests/integration/test_loop_policy.py`

- [ ] **Step 1: Write integration tests**

Create `tests/integration/test_loop_policy.py`:

```python
"""LoopPolicy 集成测试"""
import pytest
from merco.core.loop_policy import LoopPolicy, LoopDecision
from tests.conftest import MockLLMClient


class ForceExitPolicy(LoopPolicy):
    """即使有 tool_calls 也强制退出"""
    name = "force_exit"

    async def decide(self, response, state):
        return LoopDecision(action="exit", reason="forced")


@pytest.mark.asyncio
async def test_default_policy_simple_conversation(test_agent):
    """默认策略：无 tool_calls → 正常退出"""
    test_agent.llm = MockLLMClient([{"content": "hello"}])
    result = await test_agent.run("hi")
    assert result == "hello"


@pytest.mark.asyncio
async def test_default_policy_tool_call_continues(test_agent):
    """默认策略：有 tool_calls → 执行工具并继续"""
    test_agent.llm = MockLLMClient([
        {"tool_calls": [{"id": "t1", "name": "echo", "arguments": {"message": "hi"}}]},
        {"content": "done"},
    ])
    result = await test_agent.run("echo hi")
    assert result == "done"
    assert any(m.get("role") == "tool" for m in test_agent.session.messages)


@pytest.mark.asyncio
async def test_custom_policy_can_force_exit(test_agent):
    """自定义策略可影响 loop 决策"""
    test_agent.loop_policies.register(ForceExitPolicy())
    test_agent.loop_policies.set_active("force_exit")
    test_agent.llm = MockLLMClient([
        {"tool_calls": [{"id": "t1", "name": "echo", "arguments": {"message": "hi"}}], "content": "forced exit"},
    ])
    result = await test_agent.run("echo hi")
    # 强制退出，不执行工具
    assert result == "forced exit"
    assert not any(m.get("role") == "tool" for m in test_agent.session.messages)
```

- [ ] **Step 2: Modify _agent_loop**

In `merco/core/agent.py`, after `tool_calls = response.get("tool_calls")`, build state and call policy:

```python
            from merco.core.loop_policy import LoopState
            state = LoopState(
                iteration=self._tool_calls_count,
                tool_calls_count=self._tool_calls_count,
                max_tool_calls=self._max_tool_calls,
                has_tool_calls=bool(tool_calls),
                finish_reason=response.get("finish_reason"),
            )
            decision = await self.loop_policies.active.decide(response, state)
```

Then replace the existing `if not tool_calls:` condition with:

```python
            if decision.action == "exit":
                content = response.get("content", "") or ""
                content = re.sub(r'<\w+:tool_call[^>]*>.*?</\w+:tool_call>', '', content, flags=re.DOTALL).strip()
                reasoning = response.get("reasoning", "")
                if reasoning:
                    logger.debug("Agent 循环: 收到 reasoning (%d chars)，丢弃（不存入 context）", len(reasoning))
                if not content:
                    _empty_retries += 1
                    if _empty_retries == 1 and reasoning:
                        from .pipeline import EmptyResponseContext
                        ectx = EmptyResponseContext(reasoning=reasoning, retry_count=_empty_retries)
                        if await self.empty_response_pipeline.attempt(ectx):
                            if ectx.inject_error:
                                self.context.add({"role": "user", "content": ectx.inject_error})
                            console.print("[dim]   空回复  回调 LLM…[/dim]")
                            continue
                    content = reasoning or "（无回复）"
                self.session.add_message("assistant", content)
                self.context.add({"role": "assistant", "content": content})
                return content
```

Keep the rest of tool execution path unchanged. DefaultLoopPolicy makes this behavior identical to previous `if not tool_calls`.

- [ ] **Step 3: Run tests**

Run:

```bash
cd /home/xiowen/code/merco
python3 -m pytest tests/integration/test_loop_policy.py -v
python3 -m pytest tests/integration/test_scenarios.py -v -k "simple_conversation or tool_call_chain"
```

Expected: all pass

- [ ] **Step 4: Commit**

```bash
cd /home/xiowen/code/merco
git add merco/core/agent.py tests/integration/test_loop_policy.py
git commit -m "feat: Agent loop delegates exit decisions to LoopPolicy"
```

---

## Task 4: 文档更新

**Files:**
- Modify: `docs/project-vision/references/architecture-refactor-plan.md`
- Modify: `docs/project-vision/references/progress.md`

- [ ] **Step 1: Update architecture-refactor-plan.md**

Mark Phase 2.1 as complete:

```markdown
### 2.1 Agent Loop 开放 LoopPolicy ✅ 已完成
```

- [ ] **Step 2: Update progress.md**

Add a new section:

```markdown
- **LoopPolicy（架构重构 Phase 2.1）**:
  - 新增 `LoopState` / `LoopDecision` / `LoopPolicy` ABC / `DefaultLoopPolicy` / `LoopPolicyRegistry`
  - Agent 启动装配 `loop_policies` 并注入 PluginContext
  - `_agent_loop` 退出条件委托给 active policy，默认策略复刻原行为
  - 测试覆盖默认退出、tool_call 继续、自定义策略强制退出
```

- [ ] **Step 3: Commit**

```bash
cd /home/xiowen/code/merco
git add docs/project-vision/references/architecture-refactor-plan.md docs/project-vision/references/progress.md
git commit -m "docs: mark LoopPolicy refactor complete"
```

---

## Self-Review

**Spec coverage:**
- ✅ LoopState / LoopDecision (Task 1)
- ✅ LoopPolicy ABC (Task 1)
- ✅ DefaultLoopPolicy (Task 1)
- ✅ LoopPolicyRegistry (Task 1)
- ✅ PluginContext loop_policies (Task 2)
- ✅ Agent 装配 (Task 2)
- ✅ _agent_loop 调用 active policy (Task 3)
- ✅ Integration tests (Task 3)
- ✅ Docs (Task 4)

**Placeholder scan:** 无

**Behavior safety:** DefaultLoopPolicy 复刻当前行为；max_tool_calls 保持硬上限
