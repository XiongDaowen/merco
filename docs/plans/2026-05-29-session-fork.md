# 会话 Fork/分支 实现计划

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** 手动 `/fork` + 压缩自动 fork，预留会话树可视化架构。

**Architecture:** `SessionStore.clone_session()` → `Session.fork()` 工厂 → `Agent._compress_context` / `/fork` 命令 两条触发路径。

**Tech Stack:** Python 3.12+, SQLite, asyncio, typer, rich

---

### Task 1: SessionStore.clone_session() — 深克隆 SQLite 数据

**Objective:** 在 session_store.py 实现 `clone_session()` 方法：复制 sessions 行 + 全量 messages 到新 session_id。

**Files:**
- Modify: `merco/memory/session_store.py`
- Test: `tests/memory/test_session_store.py`（新建）

**Step 1: 写测试**

```python
# tests/memory/test_session_store.py
import os
import pytest
from merco.memory.session_store import SessionStore

@pytest.fixture
def store(tmp_path):
    db = str(tmp_path / "test.db")
    s = SessionStore(db)
    s.create_session("s1", "test session")
    s.save_message("s1", "user", "hello")
    s.save_message("s1", "assistant", "hi there")
    return s

def test_clone_creates_new_id(store):
    new_id = store.clone_session("s1")
    assert new_id != "s1"
    assert len(new_id) > 0

def test_clone_copies_messages(store):
    new_id = store.clone_session("s1")
    assert store.count_messages(new_id) == 2
    # 原会话消息不受影响
    assert store.count_messages("s1") == 2

def test_clone_sets_parent_id(store):
    new_id = store.clone_session("s1")
    cloned = store.load_session(new_id)
    assert cloned["parent_id"] == "s1"

def test_clone_copies_metadata(store):
    store.save_metadata("s1", {"observer": {"tokens": 100}})
    new_id = store.clone_session("s1")
    cloned = store.load_session(new_id)
    assert cloned["metadata"]["observer"]["tokens"] == 100

def test_clone_nonexistent_raises(store):
    with pytest.raises(ValueError):
        store.clone_session("does-not-exist")

def test_get_children_returns_forks(store):  # /tree 预留
    child1 = store.clone_session("s1")
    child2 = store.clone_session("s1")
    children = store.get_children("s1")
    assert len(children) >= 2
    assert child1 in [c["id"] for c in children]
```

**Step 2: 运行测试，确认失败**

```bash
uv run pytest tests/memory/test_session_store.py -v
```
Expected: FAIL — `AttributeError: 'SessionStore' object has no attribute 'clone_session'`

**Step 3: 写实现**

在 `SessionStore` 类末尾加两个方法：

```python
def clone_session(self, session_id: str) -> str:
    """深克隆会话到新 ID，返回新 session_id。原会话设 parent_id。"""
    original = self.load_session(session_id)
    if not original:
        raise ValueError(f"Session {session_id} not found")

    new_id = _new_id()
    now = _now()
    with self._conn() as conn:
        conn.execute(
            "INSERT INTO sessions (id, title, created_at, updated_at, "
            "message_count, parent_id, metadata) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (new_id, original["title"], now, now,
             original["message_count"], session_id,
             json.dumps(original.get("metadata", {}))),
        )
        # 复制全量 messages
        for msg in original.get("messages", []):
            self.save_message(
                session_id=new_id,
                role=msg["role"],
                content=msg.get("content", ""),
                tool_call_id=msg.get("tool_call_id", ""),
                tool_calls=msg.get("tool_calls"),
                reasoning=msg.get("reasoning", ""),
            )
        conn.commit()
    return new_id

def get_children(self, session_id: str) -> list[dict]:
    """查找 parent_id 指向此会话的所有子会话（为 /tree 预留）。"""
    with self._conn() as conn:
        rows = conn.execute(
            "SELECT id, title, created_at FROM sessions WHERE parent_id = ? "
            "ORDER BY created_at DESC", (session_id,)
        ).fetchall()
    return [dict(r) for r in rows]
```

**Step 4: 运行测试，确认通过**

```bash
uv run pytest tests/memory/test_session_store.py -v
```
Expected: PASS

**Step 5: Commit**

```bash
git add merco/memory/session_store.py tests/memory/test_session_store.py
git commit -m "feat(session): add clone_session + get_children to SessionStore"
```

---

### Task 2: Session.fork() 工厂方法

**Objective:** 在 `Session` 类加 `fork()` 工厂方法，包装 `store.clone_session` 返回新 Session。

**Files:**
- Modify: `merco/core/session.py`
- Test: `tests/core/test_session.py`（追加）

**Step 1: 写测试**

```python
# tests/core/test_session.py 追加
def test_fork_creates_new_session(store):
    store.create_session("s1", "original")
    s1 = Session.load("s1", store)
    s2 = Session.fork("s1", store)
    assert s2.id != s1.id

def test_fork_copies_messages(store):
    store.create_session("s1", "original")
    store.save_message("s1", "user", "hello")
    s2 = Session.fork("s1", store)
    assert len(s2.messages) == 1
    assert s2.messages[0]["content"] == "hello"

def test_fork_preserves_title(store):
    store.create_session("s1", "original")
    s2 = Session.fork("s1", store)
    assert s2.title == "original"

def test_fork_nonexistent_returns_none(store):
    result = Session.fork("does-not-exist", store)
    assert result is None
```

**Step 2: 运行测试，确认失败**

```bash
uv run pytest tests/core/test_session.py -v -k fork
```

**Step 3: 写实现**

在 `Session` 类加 `fork()` 工广方法：

```python
@classmethod
def fork(cls, session_id: str, store, title: str = None) -> "Session | None":
    """从 session_id 克隆新会话。title=None 则沿用原标题。"""
    try:
        new_id = store.clone_session(session_id)
    except (ValueError, Exception):
        return None
    if title:
        store.update_title(new_id, title)
    return cls.load(new_id, store)
```

> 注意：`update_title` 目前有 `WHERE title = ''` 条件，fork 时需要改为无条件更新。fork 传 title 时直接更新，或用一个新方法 `set_title()`。

**Step 4: 运行测试，确认通过**

```bash
uv run pytest tests/core/test_session.py -v -k fork
```

**Step 5: Commit**

```bash
git add merco/core/session.py tests/core/test_session.py
git commit -m "feat(session): add Session.fork factory method"
```

---

### Task 3: config.py — fork 配置项

**Objective:** 在 `MercoConfig` 加 `fork_enabled` + `fork_auto_on_compress`，走 `session` 命名空间。

**Files:**
- Modify: `merco/core/config.py`
- Test: `tests/unit/test_config.py`（追加）

**Step 1: 写测试**

```python
# tests/unit/test_config.py 追加
def test_session_config_defaults():
    cfg = MercoConfig()
    assert cfg.fork_enabled is True
    assert cfg.fork_auto_on_compress is True

def test_session_config_to_dict():
    cfg = MercoConfig()
    d = cfg._to_dict()
    assert d["session"]["fork_enabled"] is True
    assert d["session"]["fork_auto_on_compress"] is True

def test_session_config_from_dict():
    cfg = MercoConfig._from_dict({
        "session": {"fork_enabled": False, "fork_auto_on_compress": False}
    })
    assert cfg.fork_enabled is False
    assert cfg.fork_auto_on_compress is False
```

**Step 2: 运行测试，确认失败 → 实现 → 通过**

在 `MercoConfig` 加字段：
```python
fork_enabled: bool = True
fork_auto_on_compress: bool = True
```

`_to_dict` 加 `"session": {"fork_enabled": ..., "fork_auto_on_compress": ...}`，`_from_dict` 从 `data.get("session", {})` 读取。

**Step 3: Commit**

```bash
git add merco/core/config.py tests/unit/test_config.py
git commit -m "feat(config): add session fork config options"
```

---

### Task 4: Agent._compress_context — 自动 fork

**Objective:** 在 `Agent._compress_context()` 开头插入自动 fork 逻辑：检查配置 → save → fork → 提示。

**Files:**
- Modify: `merco/core/agent.py`
- Test: `tests/core/test_agent.py`（追加）

**Step 1: 写测试**

```python
# tests/core/test_agent.py 追加
@pytest.mark.asyncio
async def test_compress_auto_fork(agent):
    agent.config.fork_auto_on_compress = True
    agent.session.add_message("user", "test")
    # mock _compress_context to verify fork was called
    ...

@pytest.mark.asyncio
async def test_compress_no_fork_when_disabled(agent):
    agent.config.fork_auto_on_compress = False
    # verify no fork call
    ...
```

**Step 2: 写实现**

在 `agent.py` 找到 `_compress_context` 方法（或 `compress` 调用处），在压缩前加：

```python
async def _compress_context(self):
    if self.config.fork_auto_on_compress and self.config.fork_enabled:
        self.session.save()
        archived_id = self._session_store.clone_session(self.session.id)
        archived = self._session_store.load_session(archived_id)
        title = archived["title"] or archived_id[:8]
        console.print(f"[dim]📦 已归档: {title} ({archived_id[:8]})[/dim]")
    # 原有压缩逻辑...
```

**Step 3: 运行测试 → 通过 → Commit**

```bash
git add merco/core/agent.py tests/core/test_agent.py
git commit -m "feat(agent): auto-fork on context compress"
```

---

### Task 5: CLI /fork + /tree 占位

**Objective:** 加 `/fork` 命令 + `/tree` 占位 + 更新 `/help`。

**Files:**
- Modify: `cli/main.py`

**Step 1: 在 `handle_command()` 加两个分支（`/tools` 和 `else` 之间）**

```python
elif command == "/fork":
    title = parts[1].strip() if len(parts) > 1 else ""
    agent.observer.save()
    agent.session.metadata["observer"] = agent.observer.snapshot()
    agent.session.save()
    agent._session_store.save_metadata(agent.session.id, agent.session.metadata)
    
    new_session = Session.fork(agent.session.id, agent._session_store,
                               title=title or None)
    if not new_session:
        console.print("[red]Fork 失败[/red]")
        return True
    
    agent.session = new_session
    agent.observer.reset()
    agent._restore_context()
    from merco.sandbox import snapshot
    snapshot.set_current_session(agent.session.id)
    display = new_session.title or new_session.id[:8]
    console.print(f"[green]已 fork 到: {display}[/green]")
    return True

elif command == "/tree":
    children = agent._session_store.get_children(agent.session.id)
    parent = agent.session.metadata.get("parent_id")
    if not children and not parent:
        console.print("[dim]单会话，无分支[/dim]")
        return True
    if parent:
        console.print(f"[dim]父会话: {parent[:8]}[/dim]")
    if children:
        console.print("[bold]子会话:[/bold]")
        for c in children[:10]:
            console.print(f"  - {c['title'] or c['id'][:8]}  [dim]{c['created_at'][:10]}[/dim]")
    return True
```

**Step 2: 更新 `/help`，加 `/fork` 和 `/tree` 条目**

**Step 3: Commit**

```bash
git add cli/main.py
git commit -m "feat(cli): add /fork and /tree commands"
```

---

## Task Order

```
Task 1: clone_session()     ← 无依赖
Task 2: Session.fork()      ← 依赖 Task 1
Task 3: config fork options ← 无依赖
Task 4: agent auto fork     ← 依赖 Task 1+2+3
Task 5: CLI /fork /tree     ← 依赖 Task 1+2
```
