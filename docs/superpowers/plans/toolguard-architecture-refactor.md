---
name: toolguard-architecture-refactor
description: ToolGuard 架构重构：职责分离，决策与交互解耦
created: 2026-06-13
status: in_progress
---

# 实现计划：ToolGuard 架构重构

## 目标

重构 ToolGuard 架构，实现**职责分离**：
- ToolGuard：**只做决策**，返回是否需要确认
- Agent 层：**处理交互**，展示确认 Panel，获取用户输入

## 根因

当前架构问题：
- ToolGuard 自己调用 input() 做确认，**职责混乱**
- BashTool subprocess 继承 stdin，与 ToolGuard.input() **竞争 stdin**
- 两个组件职责不清，导致双重确认

## 新架构

```
LLM → Registry.execute("bash", command="rm ...")
                ↓
        ToolGuard.check() → 返回 GuardResult
                ↓
        Registry 发现需要确认 → 抛 GuardConfirmationRequired 异常
                ↓
        Agent 捕获异常 → 展示 Panel → 用户确认
                ↓
        放行 → Registry.execute 继续 → BashTool.execute()
```

## 任务清单

### 任务 1：定义 GuardResult 和异常

**文件**: `merco/sandbox/guard.py`

```python
from dataclasses import dataclass
from enum import Enum

class GuardAction(Enum):
    ALLOW = "allow"      # 直接放行
    DENY = "deny"        # 直接拒绝
    ASK = "ask"          # 需要用户确认

@dataclass
class GuardResult:
    action: GuardAction
    command: str
    rule: GuardRule | None = None
    reason: str = ""

class GuardConfirmationRequired(Exception):
    """需要用户确认的异常"""
    def __init__(self, result: GuardResult):
        self.result = result
        super().__init__(f"需要确认: {result.command}")
```

### 任务 2：修改 ToolGuard.check() 返回 GuardResult

**文件**: `merco/sandbox/guard.py`

```python
async def check(self, tool_name: str, arguments: dict) -> GuardResult:
    """检查工具是否可以执行。返回 GuardResult。"""
    command = arguments.get("command", "")
    path = arguments.get("path", "")

    # 文件工具：SecurityChecker 路径检测
    if path and tool_name != "bash":
        ok, reason = SecurityChecker.check_file_path(path)
        if not ok:
            return GuardResult(
                action=GuardAction.DENY,
                command=path,
                reason=reason
            )

    # SecurityChecker 正则兜底
    if command:
        ok, reason = SecurityChecker.check_command(command)
        if not ok:
            return GuardResult(
                action=GuardAction.DENY,
                command=command,
                reason=reason
            )

    # 规则链匹配
    for rule in self._rules:
        if not self._tool_match(rule.tool, tool_name):
            continue
        if rule.pattern not in command:
            continue

        if rule.action == "allow":
            return GuardResult(action=GuardAction.ALLOW, command=command, rule=rule)
        if rule.action == "deny":
            return GuardResult(action=GuardAction.DENY, command=command, rule=rule)
        if rule.action == "ask":
            return GuardResult(action=GuardAction.ASK, command=command, rule=rule)

    return GuardResult(action=GuardAction.ALLOW, command=command)
```

### 任务 3：修改 Registry.execute() 处理 GuardResult

**文件**: `merco/tools/registry.py`

```python
from merco.sandbox.guard import GuardResult, GuardAction, GuardConfirmationRequired

async def execute(self, tool_name: str, **kwargs) -> dict:
    tool = self.get(tool_name)
    if tool is None:
        return {"error": f"工具 '{tool_name}' 不存在"}

    from merco.sandbox import tool_guard
    result = await tool_guard.check(tool_name, kwargs)

    if result.action == GuardAction.DENY:
        return {
            "error": f"操作被安全守卫拒绝: {result.reason}",
            "tool": tool_name,
        }

    if result.action == GuardAction.ASK:
        raise GuardConfirmationRequired(result)

    # ALLOW: 直接执行
    try:
        return await tool.execute(**kwargs)
    except Exception as e:
        from merco.core.self_healing import tool_error
        return tool_error(e, tool_name, getattr(tool, 'parameters', None))
```

### 任务 4：Agent 层处理 GuardConfirmationRequired

**文件**: `merco/core/agent.py`

```python
from merco.sandbox.guard import GuardConfirmationRequired, GuardResult

# 在 execute_tool_calls 或类似位置处理
async def _execute_tool_with_guard(self, tool_name: str, **kwargs) -> dict:
    try:
        return await self.tool_registry.execute(tool_name, **kwargs)
    except GuardConfirmationRequired as e:
        # 展示确认 Panel
        confirmed = await self._ask_guard_confirmation(e.result)
        if not confirmed:
            return {"error": "用户取消了操作"}
        # 重新执行（跳过 guard）
        tool = self.tool_registry.get(tool_name)
        return await tool.execute(**kwargs)

async def _ask_guard_confirmation(self, result: GuardResult) -> bool:
    """展示安全确认 Panel 并获取用户输入"""
    from rich.console import Console
    from rich.panel import Panel

    console = Console()
    rule = result.rule

    console.print(Panel(
        f"[yellow]{result.command}[/yellow]\n"
        f"[dim]匹配规则: {rule.pattern if rule else '?'}[/dim]",
        title="⚠️ 敏感命令" if result.action.value == "ask" else "⛔ 已拒绝",
        border_style="yellow" if result.action.value == "ask" else "red",
    ))

    import asyncio
    console.print("[bold yellow]确认执行？[/bold yellow] [dim]y/N [/dim]", end="")
    resp = await asyncio.to_thread(input, "")
    return resp.strip().lower() in ("y", "yes")
```

### 任务 5：更新测试

**文件**: `tests/test_registry_guard.py`

- 更新 mock 和断言以适应 GuardResult
- 测试 GuardConfirmationRequired 异常传播

## 验收标准

1. ✅ 敏感命令只出现一次确认 Panel
2. ✅ 确认后命令正常执行
3. ✅ 拒绝后命令不执行
4. ✅ 危险命令被直接拒绝（无确认）
5. ✅ 原有测试通过

## 不在此计划范围

- `/dev/tty` 方案
- 审计日志持久化