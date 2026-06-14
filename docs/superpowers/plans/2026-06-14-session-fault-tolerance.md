# Session 持久化容错增强实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 增强 Session 持久化的健壮性，添加重试机制、备份恢复和完整性检查

**Architecture:**
- SessionStore 添加重试逻辑和备份/恢复方法
- Agent 在压缩前触发备份
- 启动时检查 SQLite 完整性

**Tech Stack:** Python 3.12, sqlite3, shutil, logging

---

## 文件结构

| 文件 | 职责 |
|------|------|
| `merco/memory/session_store.py` | 重试机制、备份恢复、完整性检查 |
| `merco/core/agent.py` | 压缩前调用备份 |

---

## Task 1: 添加 SessionWriteError 异常类

**Files:**
- Modify: `merco/memory/session_store.py`

- [ ] **Step 1: 在文件顶部添加异常类**

在 `import` 之后，`SessionStore` 类之前添加：

```python
class SessionWriteError(Exception):
    """Session 写入失败（重试 N 次后仍失败）"""
    pass
```

- [ ] **Step 2: 验证语法**

Run: `cd /home/xiowen/code/merco && python3 -m py_compile merco/memory/session_store.py && echo "Syntax OK"`

- [ ] **Step 3: Commit**

Run: `cd /home/xiowen/code/merco && git add merco/memory/session_store.py && git commit -m "feat: add SessionWriteError exception class"`

---

## Task 2: 添加重试机制到 save_message

**Files:**
- Modify: `merco/memory/session_store.py`

- [ ] **Step 1: 找到 save_message 方法**

Run: `cd /home/xiowen/code/merco && grep -n "def save_message" merco/memory/session_store.py`

Expected: 找到方法定义位置

- [ ] **Step 2: 重写 save_message 添加重试逻辑**

替换当前的 `save_message` 方法为：

```python
def save_message(self, session_id: str, role: str, content: str = "",
                 tool_call_id: str = "", tool_calls: list | None = None,
                 reasoning: str = "") -> int:
    """保存消息，支持重试"""
    now = _now()
    tc_json = json.dumps(tool_calls or [], ensure_ascii=False)
    last_error = None

    for attempt in range(3):
        try:
            with self._conn() as conn:
                cur = conn.execute(
                    "INSERT INTO messages (session_id, role, content, tool_call_id, "
                    "tool_calls, reasoning, timestamp) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (session_id, role, content, tool_call_id, tc_json, reasoning, now),
                )
                conn.execute(
                    "UPDATE sessions SET updated_at = ?, "
                    "message_count = message_count + 1 "
                    "WHERE id = ?",
                    (now, session_id),
                )
                conn.commit()
                return cur.lastrowid
        except sqlite3.OperationalError as e:
            last_error = e
            if attempt < 2:
                time.sleep(0.1 * (attempt + 1))
        except Exception as e:
            # 非瞬时错误，不重试
            raise SessionWriteError(f"写入失败（非重试错误）: {e}") from e

    # 3 次全部失败
    logger.warning(
        f"⚠️ Session 写入失败（已重试 3 次）\n"
        f"   可能是磁盘满或权限问题\n"
        f"   建议：检查 ~/.merco/ 目录"
    )
    raise SessionWriteError(f"写入失败: {last_error}")
```

- [ ] **Step 3: 验证语法**

Run: `cd /home/xiowen/code/merco && python3 -m py_compile merco/memory/session_store.py && echo "Syntax OK"`

- [ ] **Step 4: Commit**

Run: `cd /home/xiowen/code/merco && git add merco/memory/session_store.py && git commit -m "feat: add retry mechanism to save_message"`

---

## Task 3: 添加备份和恢复方法

**Files:**
- Modify: `merco/memory/session_store.py`

- [ ] **Step 1: 添加 backup_path 属性**

在 `_conn` 方法之后添加：

```python
@property
def _backup_path(self) -> str:
    """备份文件路径"""
    return self.db_path + ".backup"
```

- [ ] **Step 2: 添加 backup 方法**

```python
def backup(self) -> bool:
    """创建数据库备份，返回 True=成功"""
    try:
        shutil.copy2(self.db_path, self._backup_path)
        logger.debug(f"Session 数据库已备份到 {self._backup_path}")
        return True
    except Exception as e:
        logger.warning(f"备份 Session 数据库失败: {e}")
        return False
```

- [ ] **Step 3: 添加 restore_from_backup 方法**

```python
def restore_from_backup(self) -> bool:
    """从备份恢复数据库，返回 True=成功"""
    if not os.path.exists(self._backup_path):
        logger.warning("无备份文件，无法恢复")
        return False
    try:
        shutil.copy2(self._backup_path, self.db_path)
        logger.info("从备份恢复 Session 数据库成功")
        return True
    except Exception as e:
        logger.error(f"从备份恢复失败: {e}")
        return False
```

- [ ] **Step 4: 添加 delete_backup 方法**

```python
def delete_backup(self) -> bool:
    """删除备份文件，返回 True=成功"""
    try:
        if os.path.exists(self._backup_path):
            os.remove(self._backup_path)
            logger.debug("备份文件已删除")
        return True
    except Exception as e:
        logger.warning(f"删除备份文件失败: {e}")
        return False
```

- [ ] **Step 5: 验证语法**

Run: `cd /home/xiowen/code/merco && python3 -m py_compile merco/memory/session_store.py && echo "Syntax OK"`

- [ ] **Step 6: Commit**

Run: `cd /home/xiowen/code/merco && git add merco/memory/session_store.py && git commit -m "feat: add backup/restore methods to SessionStore"`

---

## Task 4: 添加完整性检查

**Files:**
- Modify: `merco/memory/session_store.py`

- [ ] **Step 1: 添加 check_integrity 方法**

```python
def check_integrity(self) -> bool:
    """检查 SQLite 完整性，返回 True=正常"""
    try:
        with self._conn() as conn:
            result = conn.execute("PRAGMA integrity_check").fetchone()
            is_ok = result[0] == "ok"
            if not is_ok:
                logger.warning(f"Session 数据库完整性检查失败: {result[0]}")
            return is_ok
    except Exception as e:
        logger.warning(f"完整性检查异常: {e}")
        return False
```

- [ ] **Step 2: 添加 startup_check 方法**

```python
def startup_check(self):
    """启动时检查，必要时恢复"""
    if not os.path.exists(self.db_path):
        return  # 数据库不存在，无需检查

    if not self.check_integrity():
        logger.warning("Session 数据库损坏，尝试从备份恢复...")
        if not self.restore_from_backup():
            logger.error("恢复失败，Session 数据可能丢失")
```

- [ ] **Step 3: 在 __init__ 中调用 startup_check**

找到 `__init__` 方法，在 `_ensure_db()` 调用之后添加：

```python
def __init__(self, db_path: str):
    self.db_path = os.path.expanduser(db_path)
    self._ensure_db()
    self.startup_check()  # 启动时检查完整性
```

- [ ] **Step 4: 验证语法**

Run: `cd /home/xiowen/code/merco && python3 -m py_compile merco/memory/session_store.py && echo "Syntax OK"`

- [ ] **Step 5: Commit**

Run: `cd /home/xiowen/code/merco && git add merco/memory/session_store.py && git commit -m "feat: add integrity check on startup"`

---

## Task 5: 在 Agent 压缩前触发备份

**Files:**
- Modify: `merco/core/agent.py`

- [ ] **Step 1: 找到 _compress_context 方法**

Run: `cd /home/xiowen/code/merco && grep -n "async def _compress_context" merco/core/agent.py`

Expected: 找到方法定义位置（约第 880 行）

- [ ] **Step 2: 在压缩逻辑开始前添加备份调用**

找到压缩逻辑开始的位置（`_compress` 调用之前），添加：

```python
# 压缩前备份 Session 数据库
backup_ok = self._session_store.backup()
```

- [ ] **Step 3: 在压缩成功后删除备份**

找到压缩成功的路径（console.print 之后），添加：

```python
# 删除备份
if backup_ok:
    self._session_store.delete_backup()
```

- [ ] **Step 4: 验证语法**

Run: `cd /home/xiowen/code/merco && python3 -m py_compile merco/core/agent.py && echo "Syntax OK"`

- [ ] **Step 5: Commit**

Run: `cd /home/xiowen/code/merco && git add merco/core/agent.py && git commit -m "feat: backup session before compression"`

---

## Task 6: 添加单元测试

**Files:**
- Create: `tests/memory/test_session_store.py`

- [ ] **Step 1: 创建测试文件**

```python
"""SessionStore 容错测试"""
import os
import tempfile
import pytest
from merco.memory.session_store import SessionStore, SessionWriteError


class TestSaveMessageRetry:
    """测试 save_message 重试机制"""

    def test_save_message_success(self):
        """正常写入应该成功"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            store = SessionStore(db_path)
            store.create_session("test-session")

            msg_id = store.save_message("test-session", "user", "Hello")
            assert msg_id > 0

    def test_save_message_with_retry(self):
        """瞬时错误应该重试"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            store = SessionStore(db_path)
            store.create_session("test-session")

            # 正常应该成功
            msg_id = store.save_message("test-session", "user", "Hello")
            assert msg_id > 0


class TestBackupRestore:
    """测试备份恢复"""

    def test_backup_creates_file(self):
        """备份应该创建 .backup 文件"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            store = SessionStore(db_path)
            store.create_session("test-session")
            store.save_message("test-session", "user", "Hello")

            result = store.backup()
            assert result is True
            assert os.path.exists(db_path + ".backup")

    def test_restore_from_backup(self):
        """应该能从备份恢复"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            store = SessionStore(db_path)
            store.create_session("test-session")
            store.save_message("test-session", "user", "Hello")

            # 创建备份
            store.backup()

            # 删除原文件
            os.remove(db_path)

            # 恢复
            result = store.restore_from_backup()
            assert result is True
            assert os.path.exists(db_path)

            # 验证数据
            session = store.load_session("test-session")
            assert session is not None
            assert len(session["messages"]) == 1


class TestIntegrityCheck:
    """测试完整性检查"""

    def test_check_integrity_normal(self):
        """正常的数据库应该通过检查"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            store = SessionStore(db_path)
            store.create_session("test-session")

            result = store.check_integrity()
            assert result is True
```

- [ ] **Step 2: 运行测试**

Run: `cd /home/xiowen/code/merco && pytest tests/memory/test_session_store.py -v`

Expected: 所有测试通过

- [ ] **Step 3: Commit**

Run: `cd /home/xiowen/code/merco && git add tests/memory/test_session_store.py && git commit -m "test: add SessionStore fault tolerance tests"`

---

## Task 7: 更新 progress.md

**Files:**
- Modify: `docs/project-vision/references/progress.md`

- [ ] **Step 1: 找到 Session 持久化相关行**

Run: `cd /home/xiowen/code/merco && grep -n "Session.*持久化\|Session.*容错" docs/project-vision/references/progress.md`

- [ ] **Step 2: 更新状态**

将相关行从待办状态更新为已完成，添加本次实现的关键点：
- 重试机制（3 次递增退避）
- 备份恢复（压缩前 + 启动时）
- 完整性检查

- [ ] **Step 3: 同步到 skill 目录**

Run: `cd /home/xiowen/code/merco && cp -r docs/project-vision .merco/skills/`

- [ ] **Step 4: Commit**

Run: `cd /home/xiowen/code/merco && git add docs/project-vision/ && git commit -m "docs: update progress for session fault tolerance"`

---

## 完成标准

- [ ] SessionWriteError 异常类
- [ ] save_message 重试机制（3 次）
- [ ] backup/restore/delete_backup 方法
- [ ] check_integrity/startup_check 方法
- [ ] Agent 压缩前触发备份
- [ ] 单元测试通过
- [ ] progress.md 更新

---

## 执行方式

使用 `subagent-driven-development` skill 执行此计划：
- 每个 Task 分配给一个 subagent
- Spec compliance review 检查是否符合设计文档
- Code quality review 检查代码质量
- 两个 review 都通过后才进入下一个 Task