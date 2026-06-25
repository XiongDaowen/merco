# merco Todo + SubAgent 系统 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建 merco 的 Todo 管理 + 子代理派发系统，Todo 驱动子代理执行，结果自动注入父 context

**Architecture:** TodoManager (SQLite) + SubAgentManager (继承父配置，隔离 session) + TaskTool (LLM 面向) + PluginContext 扩展

**Tech Stack:** Python 3.12, SQLite, dataclass, asyncio

---

## 文件结构

| 文件 | 职责 |
|------|------|
| `merco/todo/__init__.py` | 导出 TodoManager, TodoItem |
| `merco/todo/models.py` | TodoItem dataclass |
| `merco/todo/manager.py` | TodoManager (SQLite CRUD) |
| `merco/agents/__init__.py` | 导出 SubAgentManager |
| `merco/agents/subagent.py` | SubAgentManager |
| `merco/tools/task_tools.py` | TaskTool（激活） |
| `merco/plugins/base.py` | PluginContext 新增 todo_manager/sub_agent_manager |
| `merco/core/agent.py` | Agent 装配 TodoManager + SubAgentManager |
| `cli/commands.py` | /todos /todo /todo-done 命令 |
| `tests/todo/test_models.py` | TodoItem 单测 |
| `tests/todo/test_manager.py` | TodoManager 单测 |
| `tests/agents/test_subagent.py` | SubAgentManager 单测 |
| `tests/integration/test_todo_subagent.py` | 端到端集成测试 |

---

## Task 1: TodoItem 数据模型

**Files:**
- Create: `merco/todo/__init__.py`
- Create: `merco/todo/models.py`
- Test: `tests/todo/test_models.py`

- [ ] **Step 1: Write the failing test**

Create `tests/todo/__init__.py` (empty) and `tests/todo/test_models.py`:

```python
"""TodoItem 数据模型单测"""
from merco.todo.models import TodoItem


def test_todo_item_creation():
    """TodoItem 默认值正确"""
    item = TodoItem(id="t1", title="测试任务")
    assert item.id == "t1"
    assert item.title == "测试任务"
    assert item.description == ""
    assert item.status == "pending"
    assert item.priority == 1
    assert item.parent_id is None
    assert item.assigned_to is None
    assert item.result == ""


def test_todo_item_with_values():
    """TodoItem 自定义值"""
    item = TodoItem(
        id="t2",
        title="高优先级",
        description="详细描述",
        status="in_progress",
        priority=2,
        parent_id="t1",
        assigned_to="sub_agent_1",
        created_at="2026-06-20T00:00:00",
        updated_at="2026-06-20T00:00:00",
        result="部分结果",
    )
    assert item.priority == 2
    assert item.parent_id == "t1"
    assert item.assigned_to == "sub_agent_1"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/xiowen/code/merco && python3 -m pytest tests/todo/test_models.py -v`
Expected: ImportError (merco.todo.models not exists)

- [ ] **Step 3: Implement TodoItem**

Create `merco/todo/__init__.py`:

```python
"""Todo 管理系统"""

from .models import TodoItem
from .manager import TodoManager

__all__ = ["TodoItem", "TodoManager"]
```

Create `merco/todo/models.py`:

```python
"""TodoItem 数据模型"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TodoItem:
    """任务项"""
    id: str
    title: str
    description: str = ""
    status: str = "pending"  # pending / in_progress / completed / failed
    priority: int = 1        # 0=低 1=中 2=高
    parent_id: str | None = None
    assigned_to: str | None = None
    created_at: str = ""
    updated_at: str = ""
    result: str = ""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/xiowen/code/merco && python3 -m pytest tests/todo/test_models.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
cd /home/xiowen/code/merco
git add merco/todo/ tests/todo/
git commit -m "feat: add TodoItem dataclass"
```

---

## Task 2: TodoManager (SQLite CRUD)

**Files:**
- Create: `merco/todo/manager.py`
- Test: `tests/todo/test_manager.py`

- [ ] **Step 1: Write the failing test**

Create `tests/todo/test_manager.py`:

```python
"""TodoManager 单测"""
import pytest
from merco.todo.manager import TodoManager


@pytest.fixture
def manager(tmp_path):
    return TodoManager(str(tmp_path / "todos.db"))


def test_create_todo(manager):
    """创建任务"""
    item = manager.create("测试任务", "详细描述", priority=2)
    assert item.title == "测试任务"
    assert item.description == "详细描述"
    assert item.priority == 2
    assert item.status == "pending"
    assert item.id  # 自动生成 ID


def test_get_todo(manager):
    """获取任务"""
    item = manager.create("任务1")
    loaded = manager.get(item.id)
    assert loaded.title == "任务1"


def test_update_todo(manager):
    """更新任务"""
    item = manager.create("任务1")
    updated = manager.update(item.id, status="in_progress", result="部分结果")
    assert updated.status == "in_progress"
    assert updated.result == "部分结果"


def test_list_todos(manager):
    """列出任务"""
    manager.create("任务1")
    manager.create("任务2")
    items = manager.list()
    assert len(items) == 2


def test_list_todos_by_status(manager):
    """按状态过滤"""
    manager.create("任务1")
    item2 = manager.create("任务2")
    manager.update(item2.id, status="completed")
    items = manager.list(status="pending")
    assert len(items) == 1
    assert items[0].title == "任务1"


def test_delete_todo(manager):
    """删除任务"""
    item = manager.create("任务1")
    manager.delete(item.id)
    assert manager.get(item.id) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/xiowen/code/merco && python3 -m pytest tests/todo/test_manager.py -v`
Expected: ImportError (merco.todo.manager not exists)

- [ ] **Step 3: Implement TodoManager**

Create `merco/todo/manager.py`:

```python
"""TodoManager — SQLite 任务管理"""
from __future__ import annotations

import os
import sqlite3
import uuid
from datetime import datetime
from typing import Optional

from .models import TodoItem


class TodoManager:
    """Todo 任务管理器"""

    def __init__(self, db_path: str):
        self.db_path = os.path.expanduser(db_path)
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS todos (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    description TEXT DEFAULT '',
                    status TEXT DEFAULT 'pending',
                    priority INTEGER DEFAULT 1,
                    parent_id TEXT,
                    assigned_to TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    result TEXT DEFAULT ''
                )
            """)

    def create(self, title: str, description: str = "", priority: int = 1, parent_id: str = None) -> TodoItem:
        """创建任务"""
        now = datetime.now().isoformat()
        item = TodoItem(
            id=str(uuid.uuid4()),
            title=title,
            description=description,
            priority=priority,
            parent_id=parent_id,
            created_at=now,
            updated_at=now,
        )
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO todos VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (item.id, item.title, item.description, item.status, item.priority,
                 item.parent_id, item.assigned_to, item.created_at, item.updated_at, item.result),
            )
        return item

    def get(self, id: str) -> Optional[TodoItem]:
        """获取任务"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM todos WHERE id = ?", (id,)).fetchone()
            if not row:
                return None
            return self._row_to_item(row)

    def update(self, id: str, **kwargs) -> Optional[TodoItem]:
        """更新任务"""
        item = self.get(id)
        if not item:
            return None
        kwargs["updated_at"] = datetime.now().isoformat()
        set_clause = ", ".join(f"{k} = ?" for k in kwargs)
        values = list(kwargs.values()) + [id]
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(f"UPDATE todos SET {set_clause} WHERE id = ?", values)
        return self.get(id)

    def list(self, status: str = None, parent_id: str = None) -> list[TodoItem]:
        """列出任务"""
        query = "SELECT * FROM todos WHERE 1=1"
        params = []
        if status:
            query += " AND status = ?"
            params.append(status)
        if parent_id:
            query += " AND parent_id = ?"
            params.append(parent_id)
        query += " ORDER BY priority DESC, created_at ASC"
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(query, params).fetchall()
            return [self._row_to_item(row) for row in rows]

    def delete(self, id: str) -> None:
        """删除任务"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM todos WHERE id = ?", (id,))

    @staticmethod
    def _row_to_item(row: sqlite3.Row) -> TodoItem:
        return TodoItem(
            id=row["id"],
            title=row["title"],
            description=row["description"],
            status=row["status"],
            priority=row["priority"],
            parent_id=row["parent_id"],
            assigned_to=row["assigned_to"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            result=row["result"],
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/xiowen/code/merco && python3 -m pytest tests/todo/test_manager.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
cd /home/xiowen/code/merco
git add merco/todo/manager.py tests/todo/test_manager.py
git commit -m "feat: add TodoManager with SQLite CRUD"
```

---

## Task 3: SubAgentManager

**Files:**
- Create: `merco/agents/__init__.py`
- Create: `merco/agents/subagent.py`
- Test: `tests/agents/test_subagent.py`

- [ ] **Step 1: Write the failing test**

Create `tests/agents/__init__.py` (empty) and `tests/agents/test_subagent.py`:

```python
"""SubAgentManager 单测"""
import pytest
from unittest.mock import MagicMock, AsyncMock


class TestSubAgentManager:
    def test_create_sub_agent(self, test_agent):
        """创建子代理继承父配置"""
        from merco.agents.subagent import SubAgentManager

        manager = SubAgentManager(test_agent)
        sub_agent = manager._create_sub_agent("default")

        # 继承父的 config
        assert sub_agent.config == test_agent.config
        # 继承父的 tool_registry
        assert sub_agent.tool_registry == test_agent.tool_registry
        # 隔离 session
        assert sub_agent.session.id != test_agent.session.id

    @pytest.mark.asyncio
    async def test_dispatch_updates_todo(self, test_agent):
        """派发子代理更新 Todo 状态"""
        from merco.agents.subagent import SubAgentManager
        from merco.todo.manager import TodoManager
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            todo_manager = TodoManager(f"{td}/todos.db")
            test_agent.todo_manager = todo_manager

            manager = SubAgentManager(test_agent)
            todo = todo_manager.create("测试任务")

            # Mock 子代理执行
            mock_result = "子代理完成"
            manager._create_sub_agent = MagicMock(return_value=MagicMock(
                session=MagicMock(id="sub_1"),
                run=AsyncMock(return_value=mock_result),
            ))

            subagent_id = await manager.dispatch(todo.id, "执行任务")

            # 验证 Todo 更新
            updated = todo_manager.get(todo.id)
            assert updated.status == "completed"
            assert updated.result == mock_result
            assert updated.assigned_to == "sub_1"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/xiowen/code/merco && python3 -m pytest tests/agents/test_subagent.py -v`
Expected: ImportError

- [ ] **Step 3: Implement SubAgentManager**

Create `merco/agents/__init__.py`:

```python
"""Agent 管理"""

from .subagent import SubAgentManager

__all__ = ["SubAgentManager"]
```

Create `merco/agents/subagent.py`:

```python
"""SubAgentManager — 子代理派发"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from merco.core.agent import Agent

logger = logging.getLogger("merco.agents.subagent")


class SubAgentManager:
    """子代理派发管理器"""

    def __init__(self, parent: "Agent"):
        self._parent = parent
        self._active: dict[str, "Agent"] = {}

    async def dispatch(self, todo_id: str, prompt: str, agent_name: str = "default") -> str:
        """派发子代理执行任务，返回 subagent_id"""
        # 1. 创建子 Agent
        sub_agent = self._create_sub_agent(agent_name)

        # 2. 更新 Todo 状态
        self._parent.todo_manager.update(todo_id, status="in_progress", assigned_to=sub_agent.session.id)

        # 3. 执行子代理
        try:
            result = await sub_agent.run(prompt)
            # 4. 更新 Todo 结果
            self._parent.todo_manager.update(todo_id, status="completed", result=result)
        except Exception as e:
            logger.warning("子代理执行失败: %s", e)
            self._parent.todo_manager.update(todo_id, status="failed", result=str(e))
            result = f"Error: {e}"

        # 5. 结果注入父 context
        self._inject_result_to_parent(todo_id, result)

        # 6. 触发事件
        await self._parent.hooks.emit("subagent.completed", todo_id=todo_id, result=result)

        return sub_agent.session.id

    def _create_sub_agent(self, agent_name: str) -> "Agent":
        """创建子 Agent，继承父的配置"""
        from merco.core.agent import Agent

        # 复制父的 config/tools
        sub_agent = Agent(
            config=self._parent.config,
            tool_registry=self._parent.tool_registry,
        )
        self._active[sub_agent.session.id] = sub_agent
        return sub_agent

    def _inject_result_to_parent(self, todo_id: str, result: str):
        """把子代理结果注入父代理的 context"""
        self._parent.context.add({
            "role": "tool",
            "content": f"[Todo {todo_id}] 子代理结果:\n{result}",
            "tool_call_id": f"todo_{todo_id}",
        })
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/xiowen/code/merco && python3 -m pytest tests/agents/test_subagent.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
cd /home/xiowen/code/merco
git add merco/agents/ tests/agents/
git commit -m "feat: add SubAgentManager"
```

---

## Task 4: TaskTool 激活

**Files:**
- Modify: `merco/tools/task_tools.py`

- [ ] **Step 1: Update TaskTool**

Replace the entire `merco/tools/task_tools.py`:

```python
"""任务委派工具 - 子代理调度"""

from .base import BaseTool


class TaskTool(BaseTool):
    """委派任务给子代理"""

    name = "task"
    description = "创建任务并派发给子代理执行"
    toolset = "task"
    parameters = {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "任务标题"},
            "description": {"type": "string", "description": "详细描述"},
            "priority": {"type": "integer", "description": "优先级 0=低 1=中 2=高", "default": 1},
            "agent": {"type": "string", "description": "指定子代理名称", "default": "default"},
        },
        "required": ["title"],
    }

    def check(self) -> bool:
        """激活！"""
        return True

    async def execute(self, title: str, description: str = "", priority: int = 1, agent: str = "default") -> dict:
        # 1. 创建 Todo
        todo = self._todo_manager.create(title, description, priority)

        # 2. 派发子代理
        subagent_id = await self._sub_agent_manager.dispatch(todo.id, description, agent)

        return {
            "todo_id": todo.id,
            "subagent_id": subagent_id,
            "status": "dispatched",
        }


from .registry import tool_registry  # noqa: E402 — 模块末尾自注册
tool_registry.register(TaskTool())
```

- [ ] **Step 2: Verify syntax**

Run: `cd /home/xiowen/code/merco && python3 -m py_compile merco/tools/task_tools.py && echo "Syntax OK"`

- [ ] **Step 3: Commit**

```bash
cd /home/xiowen/code/merco
git add merco/tools/task_tools.py
git commit -m "feat: activate TaskTool"
```

---

## Task 5: PluginContext 扩展

**Files:**
- Modify: `merco/plugins/base.py`

- [ ] **Step 1: Add todo_manager and sub_agent_manager to PluginContext**

Add two new attributes to PluginContext in `merco/plugins/base.py`:

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
        observer: "Observer",
        todo_manager: "TodoManager" = None,        # 新增
        sub_agent_manager: "SubAgentManager" = None,  # 新增
    ):
        # 已有
        self.hooks = hooks
        self.tool_registry = tool_registry
        self.prompt_builder = prompt_builder
        self.recovery_pipeline = recovery_pipeline
        self.result_pipeline = result_pipeline
        self.memory_save_pipeline = memory_save_pipeline
        self.recaller = recaller
        self.config = config
        self.observer = observer
        # 新增
        self.todo_manager = todo_manager
        self.sub_agent_manager = sub_agent_manager
```

- [ ] **Step 2: Verify syntax**

Run: `cd /home/xiowen/code/merco && python3 -m py_compile merco/plugins/base.py && echo "Syntax OK"`

- [ ] **Step 3: Commit**

```bash
cd /home/xiowen/code/merco
git add merco/plugins/base.py
git commit -m "feat: extend PluginContext with todo_manager and sub_agent_manager"
```

---

## Task 6: Agent 装配

**Files:**
- Modify: `merco/core/agent.py`

- [ ] **Step 1: Add TodoManager and SubAgentManager to Agent.__init__**

After the PluginManager block in Agent.__init__, add:

```python
        # ── Todo + SubAgent 系统 ──
        from merco.todo.manager import TodoManager
        from merco.agents.subagent import SubAgentManager

        self.todo_manager = TodoManager(f"{config.memory_path}/../todos.db")
        self.sub_agent_manager = SubAgentManager(self)

        # 注入到 PluginContext
        self._plugin_ctx.todo_manager = self.todo_manager
        self._plugin_ctx.sub_agent_manager = self.sub_agent_manager
```

- [ ] **Step 2: Verify syntax**

Run: `cd /home/xiowen/code/merco && python3 -m py_compile merco/core/agent.py && echo "Syntax OK"`

- [ ] **Step 3: Commit**

```bash
cd /home/xiowen/code/merco
git add merco/core/agent.py
git commit -m "feat: wire TodoManager and SubAgentManager into Agent"
```

---

## Task 7: CLI 命令

**Files:**
- Modify: `cli/commands.py`

- [ ] **Step 1: Add /todos, /todo, /todo-done commands**

Add after the /plugins command in `cli/commands.py`:

```python
@cmd_registry.register("/todos", "列出所有任务", group="task")
async def cmd_todos(agent, args):
    """列出所有任务"""
    status_filter = args.strip() if args else None
    items = agent.todo_manager.list(status=status_filter)
    if not items:
        console.print("[dim]暂无任务[/dim]")
        return True
    console.print(f"[bold]📋 任务列表 ({len(items)} 个)[/bold]")
    console.print("─" * 50)
    for item in items:
        status_icon = {"pending": "⏳", "in_progress": "🔄", "completed": "✅", "failed": "❌"}.get(item.status, "❓")
        priority_icon = {0: "低", 1: "中", 2: "高"}.get(item.priority, "中")
        console.print(f"  {status_icon} [{item.id[:8]}] {item.title}")
        console.print(f"     [dim]优先级: {priority_icon}  状态: {item.status}[/dim]")
    return True


@cmd_registry.register("/todo", "查看任务详情", group="task")
async def cmd_todo(agent, args):
    """查看单个任务详情"""
    if not args:
        console.print("[dim]用法: /todo <id>[/dim]")
        return True
    item = agent.todo_manager.get(args.strip())
    if not item:
        console.print("[dim]任务不存在[/dim]")
        return True
    console.print(f"[bold]📋 任务详情[/bold]")
    console.print(f"  ID: {item.id}")
    console.print(f"  标题: {item.title}")
    console.print(f"  描述: {item.description or '无'}")
    console.print(f"  状态: {item.status}")
    console.print(f"  优先级: {item.priority}")
    if item.assigned_to:
        console.print(f"  分配给: {item.assigned_to}")
    if item.result:
        console.print(f"  结果: {item.result[:200]}")
    return True


@cmd_registry.register("/todo-done", "标记任务完成", group="task")
async def cmd_todo_done(agent, args):
    """标记任务完成"""
    if not args:
        console.print("[dim]用法: /todo-done <id>[/dim]")
        return True
    item = agent.todo_manager.update(args.strip(), status="completed")
    if item:
        console.print(f"[green]✅ 任务已完成:[/green] {item.title}")
    else:
        console.print("[dim]任务不存在[/dim]")
    return True
```

- [ ] **Step 2: Verify syntax**

Run: `cd /home/xiowen/code/merco && python3 -m py_compile cli/commands.py && echo "Syntax OK"`

- [ ] **Step 3: Commit**

```bash
cd /home/xiowen/code/merco
git add cli/commands.py
git commit -m "feat: /todos /todo /todo-done CLI commands"
```

---

## Task 8: 端到端集成测试

**Files:**
- Create: `tests/integration/test_todo_subagent.py`

- [ ] **Step 1: Write integration test**

Create `tests/integration/test_todo_subagent.py`:

```python
"""Todo + SubAgent 端到端集成测试"""
import pytest
from merco.todo.manager import TodoManager
from merco.agents.subagent import SubAgentManager


async def test_todo_dispatch_and_result(test_agent, tmp_path):
    """Todo 创建 → 派发子代理 → 结果注入父 context"""
    # 创建 TodoManager
    todo_manager = TodoManager(str(tmp_path / "todos.db"))
    test_agent.todo_manager = todo_manager

    # 创建 SubAgentManager
    manager = SubAgentManager(test_agent)

    # 创建 Todo
    todo = todo_manager.create("测试任务", "详细描述")

    # Mock 子代理执行
    from unittest.mock import MagicMock, AsyncMock
    mock_result = "子代理完成了任务"
    manager._create_sub_agent = MagicMock(return_value=MagicMock(
        session=MagicMock(id="sub_1"),
        run=AsyncMock(return_value=mock_result),
    ))

    # 派发
    subagent_id = await manager.dispatch(todo.id, "执行任务")

    # 验证 Todo 状态
    updated = todo_manager.get(todo.id)
    assert updated.status == "completed"
    assert updated.result == mock_result
    assert updated.assigned_to == "sub_1"

    # 验证结果注入父 context
    context_messages = test_agent.context.messages
    assert any("子代理结果" in str(m.get("content", "")) for m in context_messages)
```

- [ ] **Step 2: Run test**

Run: `cd /home/xiowen/code/merco && python3 -m pytest tests/integration/test_todo_subagent.py -v`
Expected: 1 passed

- [ ] **Step 3: Commit**

```bash
cd /home/xiowen/code/merco
git add tests/integration/test_todo_subagent.py
git commit -m "test: Todo + SubAgent end-to-end integration"
```

---

## Task 9: 文档更新

**Files:**
- Modify: `docs/project-vision/references/progress.md`

- [ ] **Step 1: Update progress.md**

Add a new section for the Todo + SubAgent system in the "本次会话更新" area.

- [ ] **Step 2: Commit**

```bash
cd /home/xiowen/code/merco
git add docs/project-vision/references/progress.md
git commit -m "docs: update progress.md for Todo + SubAgent system"
```

---

## Self-Review

**Spec coverage:**
- ✅ TodoItem dataclass (Task 1)
- ✅ TodoManager SQLite CRUD (Task 2)
- ✅ SubAgentManager (Task 3)
- ✅ TaskTool 激活 (Task 4)
- ✅ PluginContext 扩展 (Task 5)
- ✅ Agent 装配 (Task 6)
- ✅ CLI 命令 (Task 7)
- ✅ 端到端集成测试 (Task 8)
- ✅ 文档更新 (Task 9)

**Placeholder scan:** 无 TBD/TODO

**Type consistency:** TodoItem 属性名、TodoManager 方法签名、SubAgentManager API 在所有 task 中一致
