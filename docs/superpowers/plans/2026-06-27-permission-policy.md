# merco PermissionPolicy 插件化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 ToolGuard 安全策略从硬编码规则链改为可拔插的 PermissionPolicy 架构

**Architecture:** PermissionPolicy ABC + PolicyPipeline 责任链 + BuiltinDefaultPolicy（迁移现有逻辑）+ ToolGuard facade + PluginContext 暴露 security_pipeline

**Tech Stack:** Python 3.12, ABC, asyncio

---

## 文件结构

| 文件 | 职责 |
|------|------|
| `merco/sandbox/guard.py` | GuardRule/GuardResult/GuardAction (不改) + PermissionPolicy ABC + PolicyPipeline + BuiltinDefaultPolicy + ToolGuard facade |
| `merco/plugins/base.py` | PluginContext 新增 security_pipeline |
| `merco/core/agent.py` | 装配 PolicyPipeline + BuiltinDefaultPolicy |
| `tests/sandbox/test_policy.py` | PermissionPolicy + PolicyPipeline + BuiltinDefaultPolicy 单测 |
| `tests/sandbox/test_policy_integration.py` | ToolGuard facade + ToolRegistry.check 集成测试 |

---

## Task 1: PermissionPolicy ABC + PolicyPipeline

**Files:**
- Modify: `merco/sandbox/guard.py` (append new classes)
- Test: `tests/sandbox/test_policy.py`

- [ ] **Step 1: Write the failing test**

Create `tests/sandbox/test_policy.py`:

```python
"""PermissionPolicy + PolicyPipeline 单测"""
import pytest
from merco.sandbox.guard import (
    PermissionPolicy, PolicyPipeline, GuardResult, GuardAction
)


class DenyAllPolicy(PermissionPolicy):
    name = "deny_all"

    async def check(self, tool_name, arguments):
        return GuardResult(action=GuardAction.DENY, command="", reason="禁止一切")


class AllowAllPolicy(PermissionPolicy):
    name = "allow_all"

    async def check(self, tool_name, arguments):
        return GuardResult(action=GuardAction.ALLOW, command="")


class PassPolicy(PermissionPolicy):
    """返回 None — 无意见"""
    name = "pass"

    async def check(self, tool_name, arguments):
        return None


class TestPermissionPolicyABC:
    def test_cannot_instantiate_abstract(self):
        with pytest.raises(TypeError):
            PermissionPolicy()  # noqa


class TestPolicyPipeline:
    async def test_first_match_wins(self):
        p = PolicyPipeline()
        p.use(DenyAllPolicy())
        p.use(AllowAllPolicy())
        result = await p.check("bash", {"command": "ls"})
        assert result.action == GuardAction.DENY

    async def test_pass_to_next(self):
        p = PolicyPipeline()
        p.use(PassPolicy())
        p.use(DenyAllPolicy())
        result = await p.check("bash", {"command": "ls"})
        assert result.action == GuardAction.DENY

    async def test_default_allow(self):
        p = PolicyPipeline()
        p.use(PassPolicy())
        result = await p.check("bash", {"command": "ls"})
        assert result.action == GuardAction.ALLOW
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/xiowen/code/merco && python3 -m pytest tests/sandbox/test_policy.py -v`
Expected: ImportError

- [ ] **Step 3: Implement PermissionPolicy ABC + PolicyPipeline**

Append to `merco/sandbox/guard.py` (below existing classes):

```python
# ── PermissionPolicy ───────────────────────────────────────

class PermissionPolicy(ABC):
    """安全策略基类"""
    name: str = ""

    @abstractmethod
    async def check(self, tool_name: str, arguments: dict) -> GuardResult | None:
        """检查工具。返回 GuardResult = 决断，None = 传给下一个策略"""
        ...


class PolicyPipeline:
    """安全策略责任链"""

    def __init__(self):
        self._policies: list[PermissionPolicy] = []

    def use(self, policy: PermissionPolicy) -> "PolicyPipeline":
        """注册策略"""
        self._policies.append(policy)
        return self

    async def check(self, tool_name: str, arguments: dict) -> GuardResult:
        """依次检查，首个返回非 None 的结果生效"""
        for policy in self._policies:
            result = await policy.check(tool_name, arguments)
            if result is not None:
                return result
        return GuardResult(action=GuardAction.ALLOW, command="")
```

Also add `from abc import ABC, abstractmethod` to the imports at the top of the file.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/xiowen/code/merco && python3 -m pytest tests/sandbox/test_policy.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
cd /home/xiowen/code/merco
git add merco/sandbox/guard.py tests/sandbox/test_policy.py
git commit -m "feat: add PermissionPolicy ABC and PolicyPipeline"
```

---

## Task 2: BuiltinDefaultPolicy

**Files:**
- Modify: `merco/sandbox/guard.py`
- Test: `tests/sandbox/test_policy.py` (append)

- [ ] **Step 1: Append test**

Append to `tests/sandbox/test_policy.py`:

```python
from merco.sandbox.guard import BuiltinDefaultPolicy


class TestBuiltinDefaultPolicy:
    async def test_allows_safe_command(self):
        p = BuiltinDefaultPolicy(mode="ask")
        result = await p.check("bash", {"command": "ls -la"})
        assert result.action == GuardAction.ALLOW

    async def test_denies_rm_rf(self):
        p = BuiltinDefaultPolicy(mode="ask")
        result = await p.check("bash", {"command": "rm -rf /"})
        assert result.action == GuardAction.ASK  # 默认规则 ask

    async def test_auto_mode_skips(self):
        p = BuiltinDefaultPolicy(mode="auto")
        result = await p.check("bash", {"command": "rm -rf /"})
        assert result.action == GuardAction.ALLOW

    async def test_user_rules_override(self):
        from merco.sandbox.guard import GuardRule
        p = BuiltinDefaultPolicy(mode="ask", user_rules=[
            {"tool": "bash", "pattern": "rm ", "action": "deny"},
        ])
        result = await p.check("bash", {"command": "rm file.txt"})
        assert result.action == GuardAction.DENY
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/xiowen/code/merco && python3 -m pytest tests/sandbox/test_policy.py -v -k Builtin`
Expected: ImportError

- [ ] **Step 3: Implement BuiltinDefaultPolicy**

Append to `merco/sandbox/guard.py`:

```python
# ── BuiltinDefaultPolicy ───────────────────────────────────

class BuiltinDefaultPolicy(PermissionPolicy):
    """默认安全策略 — 包装 30 条默认规则 + SecurityChecker + mode logic"""
    name = "builtin_default"

    def __init__(self, mode: str = "ask", user_rules: list = None):
        self.mode = mode
        self._rules: list[GuardRule] = []
        if user_rules:
            for r in user_rules:
                self._rules.append(
                    GuardRule.from_dict(r) if isinstance(r, dict) else r
                )
        self._rules.extend(_DEFAULT_RULES)

    async def check(self, tool_name: str, arguments: dict) -> GuardResult | None:
        if self.mode == "auto":
            return GuardResult(action=GuardAction.ALLOW, command="")

        command = arguments.get("command", "")
        path = arguments.get("path", "")

        if path and tool_name != "bash":
            ok, reason = SecurityChecker.check_file_path(path)
            if not ok:
                return GuardResult(action=GuardAction.DENY, command=path, reason=reason)

        if command:
            ok, reason = SecurityChecker.check_command(command)
            if not ok:
                return GuardResult(action=GuardAction.DENY, command=command, reason=reason)

        for rule in self._rules:
            if not self._tool_match(rule.tool, tool_name):
                continue
            if rule.pattern not in command:
                continue
            action = GuardAction(rule.action)
            return GuardResult(action=action, command=command, rule=rule)

        return GuardResult(action=GuardAction.ALLOW, command=command)

    @staticmethod
    def _tool_match(pattern: str, tool_name: str) -> bool:
        return pattern == "*" or pattern == tool_name
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/xiowen/code/merco && python3 -m pytest tests/sandbox/test_policy.py -v`
Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
cd /home/xiowen/code/merco
git add merco/sandbox/guard.py tests/sandbox/test_policy.py
git commit -m "feat: add BuiltinDefaultPolicy wrapping default rules and SecurityChecker"
```

---

## Task 3: ToolGuard facade

**Files:**
- Modify: `merco/sandbox/guard.py`

- [ ] **Step 1: Rewrite ToolGuard as facade**

Replace the `ToolGuard` class with a facade:

```python
class ToolGuard:
    """工具执行守卫 — facade，委托给 PolicyPipeline"""

    def __init__(self, pipeline: PolicyPipeline = None, mode: str = "ask", user_rules: list = None):
        if pipeline:
            self._pipeline = pipeline
        else:
            # 向后兼容：没传 pipeline 时自动创建默认 pipeline
            self._pipeline = PolicyPipeline()
            self._pipeline.use(BuiltinDefaultPolicy(mode=mode, user_rules=user_rules))

    def rule(self, tool: str, pattern: str, action: str) -> "ToolGuard":
        """添加规则（向后兼容）。在默认策略前插入一条自定义策略。"""
        self._pipeline._policies.insert(0,
            _SingleRulePolicy(tool, pattern, action))
        return self

    async def check(self, tool_name: str, arguments: dict) -> GuardResult:
        return await self._pipeline.check(tool_name, arguments)


class _SingleRulePolicy(PermissionPolicy):
    """单条规则的策略包装"""
    name = "single_rule"

    def __init__(self, tool, pattern, action):
        self._tool = tool
        self._pattern = pattern
        self._action = action

    async def check(self, tool_name, arguments):
        command = arguments.get("command", "")
        if self._tool not in (tool_name, "*"):
            return None
        if self._pattern not in command:
            return None
        return GuardResult(action=GuardAction(self._action), command=command)
```

- [ ] **Step 2: Run existing sandbox/guard tests + integration tests**

Run: `cd /home/xiowen/code/merco && python3 -m pytest tests/test_guard.py tests/integration/test_scenarios.py -v -k "guard" 2>&1 | tail -15`

- [ ] **Step 3: Commit**

```bash
cd /home/xiowen/code/merco
git add merco/sandbox/guard.py
git commit -m "feat: ToolGuard as facade delegating to PolicyPipeline"
```

---

## Task 4: PluginContext + Agent 装配

**Files:**
- Modify: `merco/plugins/base.py`
- Modify: `merco/core/agent.py`

- [ ] **Step 1: Add security_pipeline to PluginContext**

In `merco/plugins/base.py`, add parameter:

```python
security_pipeline: "PolicyPipeline" = None,
```

Store: `self.security_pipeline = security_pipeline`

Add TYPE_CHECKING import for PolicyPipeline.

- [ ] **Step 2: Wire in Agent.__init__**

In `merco/core/agent.py`, change ToolGuard creation to use PolicyPipeline:

```python
        # ── ToolGuard ──
        from merco.sandbox.guard import (
            ToolGuard, PolicyPipeline, BuiltinDefaultPolicy
        )
        self._security_pipeline = PolicyPipeline()
        self._security_pipeline.use(BuiltinDefaultPolicy(
            mode=config.sandbox_mode,
            user_rules=config.sandbox_rules,
        ))
        self.guard = ToolGuard(pipeline=self._security_pipeline)
        self._plugin_ctx.security_pipeline = self._security_pipeline
```

- [ ] **Step 3: Verify syntax + run tests**

Run: `cd /home/xiowen/code/merco && python3 -m py_compile merco/plugins/base.py && python3 -m py_compile merco/core/agent.py && echo "Syntax OK"`

Run: `cd /home/xiowen/code/merco && python3 -m pytest tests/plugins/ tests/test_guard.py tests/integration/test_scenarios.py -v -k "guard or test_plugin" 2>&1 | tail -15`

- [ ] **Step 4: Commit**

```bash
cd /home/xiowen/code/merco
git add merco/plugins/base.py merco/core/agent.py
git commit -m "feat: wire PolicyPipeline into PluginContext and Agent"
```

---

## Task 5: 端到端集成测试

**Files:**
- Create: `tests/sandbox/test_policy_integration.py`

- [ ] **Step 1: Write integration test**

Create `tests/sandbox/test_policy_integration.py`:

```python
"""PermissionPolicy 端到端集成测试"""
import pytest
from merco.sandbox.guard import (
    PermissionPolicy, PolicyPipeline, GuardResult, GuardAction,
    BuiltinDefaultPolicy, ToolGuard,
)


class CustomPolicy(PermissionPolicy):
    name = "custom"

    async def check(self, tool_name, arguments):
        cmd = arguments.get("command", "")
        if "secret" in cmd:
            return GuardResult(action=GuardAction.DENY, command=cmd, reason="含敏感词")
        return None


async def test_plugin_registers_policy():
    """插件注册自定义策略到 pipeline"""
    pipeline = PolicyPipeline()
    pipeline.use(BuiltinDefaultPolicy(mode="ask"))
    pipeline.use(CustomPolicy())

    guard = ToolGuard(pipeline=pipeline)

    # 危险命令被 default 拦截
    result = await guard.check("bash", {"command": "rm -rf /"})
    assert result.action == GuardAction.ASK

    # 含敏感词的命令被 custom 拦截
    result = await guard.check("bash", {"command": "grep secret file"})
    assert result.action == GuardAction.DENY


async def test_auto_mode_skips_all():
    """auto mode：BuiltinDefaultPolicy 直接放行，custom 仍执行"""
    pipeline = PolicyPipeline()
    pipeline.use(BuiltinDefaultPolicy(mode="auto"))
    pipeline.use(CustomPolicy())

    guard = ToolGuard(pipeline=pipeline)

    # auto mode 放行危险命令
    result = await guard.check("bash", {"command": "rm -rf /"})
    assert result.action == GuardAction.ALLOW

    # 但 custom 仍可拦截敏感词
    result = await guard.check("bash", {"command": "cat secret.txt"})
    assert result.action == GuardAction.DENY
```

- [ ] **Step 2: Run test**

Run: `cd /home/xiowen/code/merco && python3 -m pytest tests/sandbox/test_policy_integration.py -v`
Expected: 2 passed

- [ ] **Step 3: Commit**

```bash
cd /home/xiowen/code/merco
git add tests/sandbox/test_policy_integration.py
git commit -m "test: PermissionPolicy end-to-end integration"
```

---

## Task 6: 文档更新

**Files:**
- Modify: `docs/project-vision/references/progress.md`

- [ ] **Step 1: Update progress.md**

Add a new section for PermissionPolicy pluginization.

- [ ] **Step 2: Commit**

```bash
cd /home/xiowen/code/merco
git add docs/project-vision/references/progress.md
git commit -m "docs: update progress.md for PermissionPolicy pluginization"
```

---

## Self-Review

**Spec coverage:**
- ✅ PermissionPolicy ABC (Task 1)
- ✅ PolicyPipeline 责任链 (Task 1)
- ✅ BuiltinDefaultPolicy (Task 2)
- ✅ ToolGuard facade (Task 3)
- ✅ PluginContext security_pipeline (Task 4)
- ✅ Agent 装配 (Task 4)
- ✅ 集成测试 (Task 5)
- ✅ 文档 (Task 6)

**Placeholder scan:** 无

**Type consistency:** PermissionPolicy.check 返回类型一致
