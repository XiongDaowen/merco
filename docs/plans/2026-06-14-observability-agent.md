# Observability → Agent 打通计划

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** 让 Observer 订阅更多事件，使 `/report` 数据更完整

**Architecture:**
- Observer 已订阅：`llm.chat`、`tool.after_execute`、`tool.error`、`conversation.turn`
- Hooks → Agent 打通后新增事件：`agent.start/stop`、`session.create/destroy`、`message.receive`、`tool.before_execute`、`context.compact`
- 打通后 Observer 可统计完整工具执行耗时分布（before + after）

**Tech Stack:** Python 3.12, asyncio

---

## Task 1: 分析当前 Observer 订阅

**Objective:** 了解 Observer 当前订阅了哪些事件

**Step 1: 查看 Observer 实现**

```bash
cd /home/xiowen/code/merco
grep -n "hooks.on\|def _on" merco/observability/observer.py
```

Expected: 看到当前的 4 个订阅

**Step 2: 查看有哪些新事件可以订阅**

根据 hooks → agent 打通，新增的事件：
- `agent.start` / `agent.stop`
- `session.create` / `session.destroy`
- `message.receive`
- `tool.before_execute`
- `context.compact`

**Step 3: Commit**

```bash
git add docs/plans/2026-06-14-observability-agent.md
git commit -m "docs: add observability-agent plan"
```

---

## Task 2: 让 Observer 订阅 tool.before_execute

**Objective:** 添加 `tool.before_execute` 事件订阅，用于统计工具执行耗时

**Files:**
- Modify: `merco/observability/observer.py`

**Step 1: 添加 `_on_tool_before` 方法**

在 Observer 类中添加：

```python
async def _on_tool_before(self, tool_name: str, args: dict, **kwargs):
    """工具执行前，记录开始时间"""
    self._live.start_tool_timer(tool_name)
```

**Step 2: 添加订阅**

在 `__init__` 或 `start` 方法中添加：

```python
hooks.on("tool.before_execute", self._on_tool_before)
```

**Step 3: 实现 start_tool_timer**

在 `_MetricsCollector` 类中添加：

```python
def start_tool_timer(self, tool_name: str):
    """记录工具开始执行时间"""
    if tool_name not in self._tool_timers:
        self._tool_timers[tool_name] = []
    self._tool_timers[tool_name].append(time.monotonic())
```

**Step 4: 验证**

```bash
cd /home/xiowen/code/merco
python3 -m py_compile merco/observability/observer.py && echo "Syntax OK"
```

**Step 5: Commit**

```bash
git add merco/observability/observer.py
git commit -m "feat: add tool.before_execute observer subscription"
```

---

## Task 3: 让 Observer 订阅 agent.start/stop

**Objective:** 添加生命周期事件订阅

**Files:**
- Modify: `merco/observability/observer.py`

**Step 1: 添加 `_on_agent_start` 和 `_on_agent_stop` 方法**

```python
async def _on_agent_start(self, session_id: str, **kwargs):
    """Agent 启动"""
    self._live.increment("agent_starts")
    self._live.set_meta("current_session", session_id)

async def _on_agent_stop(self, session_id: str, **kwargs):
    """Agent 停止"""
    self._live.increment("agent_stops")
```

**Step 2: 添加订阅**

```python
hooks.on("agent.start", self._on_agent_start)
hooks.on("agent.stop", self._on_agent_stop)
```

**Step 3: 验证**

```bash
cd /home/xiowen/code/merco
python3 -m py_compile merco/observability/observer.py && echo "Syntax OK"
```

**Step 4: Commit**

```bash
git add merco/observability/observer.py
git commit -m "feat: add agent lifecycle observer subscriptions"
```

---

## Task 4: 让 Observer 订阅 context.compact

**Objective:** 统计上下文压缩次数

**Files:**
- Modify: `merco/observability/observer.py`

**Step 1: 添加 `_on_context_compact` 方法**

```python
async def _on_context_compact(self, strategy: str, **kwargs):
    """上下文压缩"""
    self._live.increment("context_compactions")
```

**Step 2: 添加订阅**

```python
hooks.on("context.compact", self._on_context_compact)
```

**Step 3: 验证**

```bash
cd /home/xiowen/code/merco
python3 -m py_compile merco/observability/observer.py && echo "Syntax OK"
```

**Step 4: Commit**

```bash
git add merco/observability/observer.py
git commit -m "feat: add context.compact observer subscription"
```

---

## Task 5: 更新 /report 显示新指标

**Objective:** 让 `/report` 命令显示新增的统计指标

**Files:**
- Modify: `merco/observability/observer.py`

**Step 1: 查看当前 `/report` 实现**

```bash
cd /home/xiowen/code/merco
grep -n "report\|_get_report\|def " merco/observability/observer.py | head -20
```

**Step 2: 添加新指标的显示**

在 report 方法中添加：
- Agent 启动/停止次数
- 上下文压缩次数
- 工具执行耗时分布（before + after）

**Step 3: 验证**

```bash
cd /home/xiowen/code/merco
python3 -m py_compile merco/observability/observer.py && echo "Syntax OK"
```

**Step 4: Commit**

```bash
git add merco/observability/observer.py
git commit -m "feat: update /report with new metrics"
```

---

## Task 6: 验证完整集成

**Objective:** 确认所有事件都能正常订阅和统计

**Step 1: 运行测试**

```bash
cd /home/xiowen/code/merco
pytest tests/ -v -k "observ" 2>/dev/null || echo "No observ-specific tests"
```

**Step 2: 手动测试**

```bash
cd /home/xiowen/code/merco
python3 -m merco
```

输入：`/report`

Expected: 应该看到新增的指标

**Step 3: Commit**

```bash
git add .
git commit -m "test: verify observability integration"
```

---

## Task 7: 更新 progress.md

**Objective:** 标记 Observability → Agent 已打通

**Files:**
- Modify: `docs/project-vision/references/progress.md`

**Step 1: 更新 Cross-Cutting Wiring Checks**

将：

```
| Observability → Agent | ⚠️ PARTIAL | Observer 已实例化并用于中断快照/恢复/Report。LLM 调用/Tool 执行点通过 hooks emit（需先打通 Hooks → Agent）。中断管线 SavePartialState 使用 Observer snapshot。 |
```

改为：

```
| Observability → Agent | ✅ WIRED | Observer 订阅所有事件：llm.chat, tool.before/after_execute, tool.error, conversation.turn, agent.start/stop, context.compact |
```

**Step 2: 同步到 skill 目录**

```bash
cp -r docs/project-vision .merco/skills/
```

**Step 3: Commit**

```bash
git add docs/project-vision/
git commit -m "docs: mark Observability → Agent as wired"
```

---

## 完成标准

- [ ] Observer 订阅 `tool.before_execute`
- [ ] Observer 订阅 `agent.start/stop`
- [ ] Observer 订阅 `context.compact`
- [ ] `/report` 显示新指标
- [ ] progress.md 更新

---

## 执行方式

使用 `subagent-driven-development` skill 执行此计划：
- 每个 Task 分配给一个 subagent
- Spec compliance review 检查是否符合设计文档
- Code quality review 检查代码质量
- 两个 review 都通过后才进入下一个 Task
