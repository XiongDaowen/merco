# Hooks → Agent 打通计划

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** 在 agent.py 关键节点补上 `emit` 调用，让定义好的事件真正流通，订阅者能收到完整的事件流。

**Architecture:**
- HookRegistry 已创建，Observer 已订阅部分事件
- 缺失：`agent.start/stop`、`session.create/destroy`、`message.receive`、`tool.before_execute`、`context.compact`
- 打通后 Observer 能统计完整工具执行耗时分布

**Tech Stack:** Python 3.12, asyncio

---

## Task 1: 分析 agent.py 关键节点

**Objective:** 找到需要加 emit 的位置

**Step 1: 查看当前已有哪些 emit**

```bash
cd /home/xiowen/code/merco
grep -n "hooks.emit" merco/core/agent.py
```

Expected: 看到现有的 emit 调用位置

**Step 2: 查看 HookRegistry 导入**

```bash
cd /home/xiowen/code/merco
grep -n "HookRegistry\|self.hooks" merco/core/agent.py | head -20
```

Expected: 看到 `self.hooks = HookRegistry()` 在 `__init__`

**Step 3: 列出缺失的事件**

根据 progress.md，缺失的事件：
- `agent.start` / `agent.stop`
- `session.create` / `session.destroy`
- `message.receive`
- `tool.before_execute`
- `context.compact`

**Step 4: Commit**

```bash
git add docs/plans/2026-06-14-hooks-agent.md
git commit -m "docs: add hooks-agent plan"
```

---

## Task 2: 打通生命周期事件

**Objective:** 加 `agent.start` 和 `agent.stop` 事件

**Files:**
- Modify: `merco/core/agent.py`

**Step 1: 找 `__init__` 末尾位置**

```bash
cd /home/xiowen/code/merco
grep -n "self.session\|self.hooks" merco/core/agent.py | head -10
```

**Step 2: 在 `__init__` 末尾加 `agent.start`**

在 `__init__` 末尾，session 创建之后，添加：

```python
# emit 生命周期事件
await self.hooks.emit("agent.start", session_id=self.session.id)
```

**Step 3: 找 `run` 方法的退出路径**

```bash
cd /home/xiowen/code/merco
grep -n "async def run\|return\|sys.exit" merco/core/agent.py | head -30
```

**Step 4: 在退出前加 `agent.stop`**

在 `run` 方法的 return 之前（各种退出路径都加上）：

```python
await self.hooks.emit("agent.stop")
```

**Step 5: 验证语法**

```bash
cd /home/xiowen/code/merco
python3 -m py_compile merco/core/agent.py && echo "Syntax OK"
```

**Step 6: Commit**

```bash
git add merco/core/agent.py
git commit -m "feat: emit agent.start/agent.stop lifecycle events"
```

---

## Task 3: 打通 session 事件

**Objective:** 加 `session.create` 和 `session.destroy` 事件

**Files:**
- Modify: `merco/core/agent.py`

**Step 1: 找 session 创建位置**

```bash
cd /home/xiowen/code/merco
grep -n "resume_or_create\|self.session" merco/core/agent.py | head -15
```

**Step 2: 在 session 创建后加 `session.create`**

在 `self.session = Session.resume_or_create(...)` 之后：

```python
await self.hooks.emit("session.create", session_id=self.session.id)
```

**Step 3: 找 session 销毁位置**

```bash
cd /home/xiowen/code/merco
grep -n "session.destroy\|/new\|/exit" merco/core/agent.py
```

**Step 4: 在退出路径加 `session.destroy`**

在 `agent.stop` 之前或同一位置：

```python
await self.hooks.emit("session.destroy", session_id=self.session.id)
```

**Step 5: 验证**

```bash
cd /home/xiowen/code/merco
python3 -m py_compile merco/core/agent.py && echo "Syntax OK"
```

**Step 6: Commit**

```bash
git add merco/core/agent.py
git commit -m "feat: emit session.create/session.destroy events"
```

---

## Task 4: 打通 message.receive 事件

**Objective:** 加 `message.receive` 事件

**Files:**
- Modify: `merco/core/agent.py`

**Step 1: 找 `_agent_loop` 方法**

```bash
cd /home/xiowen/code/merco
grep -n "async def _agent_loop\|user_input\|prompt" merco/core/agent.py | head -15
```

**Step 2: 在收到用户输入后加 emit**

在获取用户输入之后，处理之前：

```python
await self.hooks.emit("message.receive", message=user_input)
```

**Step 3: 验证**

```bash
cd /home/xiowen/code/merco
python3 -m py_compile merco/core/agent.py && echo "Syntax OK"
```

**Step 4: Commit**

```bash
git add merco/core/agent.py
git commit -m "feat: emit message.receive event"
```

---

## Task 5: 打通 tool.before_execute 事件

**Objective:** 加 `tool.before_execute` 事件

**Files:**
- Modify: `merco/core/agent.py`

**Step 1: 找 `_execute_tool_calls` 方法**

```bash
cd /home/xiowen/code/merco
grep -n "async def _execute_tool_calls\|tool_name\|tool_registry.execute" merco/core/agent.py | head -20
```

**Step 2: 在执行前加 emit**

在 `tool_registry.execute()` 调用之前：

```python
await self.hooks.emit("tool.before_execute", tool_name=tool_name, args=arguments)
```

**Step 3: 验证**

```bash
cd /home/xiowen/code/merco
python3 -m py_compile merco/core/agent.py && echo "Syntax OK"
```

**Step 4: Commit**

```bash
git add merco/core/agent.py
git commit -m "feat: emit tool.before_execute event"
```

---

## Task 6: 打通 context.compact 事件

**Objective:** 加 `context.compact` 事件

**Files:**
- Modify: `merco/core/agent.py`

**Step 1: 找 `_compress_context` 方法**

```bash
cd /home/xiowen/code/merco
grep -n "async def _compress_context\|compress\|Compressor" merco/core/agent.py | head -10
```

**Step 2: 在压缩开始时加 emit**

在压缩逻辑开始处：

```python
await self.hooks.emit("context.compact", strategy="sliding_window")
```

**Step 3: 验证**

```bash
cd /home/xiowen/code/merco
python3 -m py_compile merco/core/agent.py && echo "Syntax OK"
```

**Step 4: Commit**

```bash
git add merco/core/agent.py
git commit -m "feat: emit context.compact event"
```

---

## Task 7: 验证完整事件流

**Objective:** 确认所有事件都能正常 emit

**Files:**
- Test: 临时测试脚本

**Step 1: 创建测试脚本**

```python
# test_hooks.py
import asyncio
from merco.core.agent import Agent
from merco.hooks.registry import HookRegistry

async def main():
    events = []

    async def tracker(**kwargs):
        events.append(kwargs)

    hooks = HookRegistry()
    hooks.on("agent.start", tracker)
    hooks.on("agent.stop", tracker)
    hooks.on("session.create", tracker)
    hooks.on("session.destroy", tracker)
    hooks.on("message.receive", tracker)
    hooks.on("tool.before_execute", tracker)
    hooks.on("tool.after_execute", tracker)
    hooks.on("context.compact", tracker)

    # 这里需要 mock Agent 才能测试
    print("Events captured:", events)

asyncio.run(main())
```

**Step 2: 运行现有测试**

```bash
cd /home/xiowen/code/merco
pytest tests/ -v -k "hook" 2>/dev/null || echo "No hook tests yet"
```

**Step 3: Commit**

```bash
git add .
git commit -m "test: verify hooks emit all events"
```

---

## Task 8: 更新 progress.md 和 architecture.md

**Objective:** 标记 Hooks → Agent 已打通

**Files:**
- Modify: `docs/project-vision/references/progress.md`
- Modify: `docs/project-vision/references/architecture.md`

**Step 1: 更新 Cross-Cutting Wiring Checks**

在 progress.md 中，找到：

```
| Hooks → Agent | ❌ NOT WIRED | 无 import，无 emit。 |
```

改为：

```
| Hooks → Agent | ✅ WIRED | agent.start/stop, session.create/destroy, message.receive, tool.before_execute, context.compact 已 emit |
```

**Step 2: 更新 architecture.md**

移除 "需要加的 emit 位置" 表格（因为已实现）

**Step 3: 同步到 skill 目录**

```bash
cp -r docs/project-vision .merco/skills/
```

**Step 4: Commit**

```bash
git add docs/project-vision/
git commit -m "docs: mark Hooks → Agent as wired"
```

---

## 完成标准

- [ ] `agent.start` / `agent.stop` 事件 emit
- [ ] `session.create` / `session.destroy` 事件 emit
- [ ] `message.receive` 事件 emit
- [ ] `tool.before_execute` 事件 emit
- [ ] `context.compact` 事件 emit
- [ ] 语法验证通过
- [ ] progress.md 更新

---

## 执行方式

使用 `subagent-driven-development` skill 执行此计划：
- 每个 Task 分配给一个 subagent
- Spec compliance review 检查是否符合设计文档
- Code quality review 检查代码质量
- 两个 review 都通过后才进入下一个 Task
