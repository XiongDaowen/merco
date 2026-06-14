# Session 持久化容错增强设计

> 最后更新: 2026-06-14

## 目标

增强 Session 持久化的健壮性，处理以下问题：
1. **消息丢失** — 写入失败导致对话历史丢失
2. **数据库损坏** — SQLite 文件损坏导致 session 无法恢复
3. **写入失败无提示** — 用户不知道数据没存上

## 当前状态

SessionStore 使用 SQLite WAL 模式：
- `save_message()`: 写入消息 + 更新 message_count，无重试
- `clone_session()`: 完整的原子操作（事务）
- `_conn()`: 每次创建新连接
- 无重试机制
- 无备份机制

## 解决方案

### 1. 写入重试机制

**目标**：覆盖瞬时问题（如锁竞争）

**实现**：
```python
def save_message(self, session_id, ...) -> int:
    last_error = None
    for attempt in range(3):
        try:
            # 写入逻辑
            return cur.lastrowid
        except sqlite3.OperationalError as e:
            last_error = e
            if attempt < 2:
                time.sleep(0.1 * (attempt + 1))
    # 3 次全部失败
    raise SessionWriteError(f"写入失败: {last_error}")
```

**重试条件**：`sqlite3.OperationalError`（锁、忙等瞬时错误）

**重试间隔**：0.1s、0.2s、0.3s（递增退避）

### 2. 备份恢复机制

**时机**：

| 时机 | 行为 |
|------|------|
| 压缩前 | `cp sessions.db sessions.db.backup` |
| 启动时 | 检查完整性，损坏则恢复备份 |
| 异常时 | 捕获 SQLite 异常，尝试恢复备份 |
| 成功后 | `rm sessions.db.backup` |

**备份文件**：`sessions.db.backup`（同目录）

**恢复逻辑**：
```python
def restore_from_backup(self):
    """从备份恢复 SQLite"""
    backup_path = self.db_path + ".backup"
    if os.path.exists(backup_path):
        shutil.copy2(backup_path, self.db_path)
        logger.info("从备份恢复 Session 数据库")
```

### 3. 启动完整性检查

```python
def check_integrity(self) -> bool:
    """检查 SQLite 完整性，返回 True=正常"""
    try:
        with self._conn() as conn:
            result = conn.execute("PRAGMA integrity_check").fetchone()
            return result[0] == "ok"
    except Exception:
        return False

def startup_check(self):
    """启动时检查，必要时恢复"""
    if not self.check_integrity():
        self.restore_from_backup()
```

### 4. 用户提示

```python
# 重试全部失败后
logger.warning(
    "⚠️ Session 写入失败（已重试 3 次）\n"
    "   可能是磁盘满或权限问题\n"
    "   建议：检查 ~/.merco/ 目录"
)
```

### 5. 事务保证

`save_message` 和 `update_message_count` 必须在同一事务中：

```python
def save_message(self, session_id, ...) -> int:
    with self._conn() as conn:
        cur = conn.execute("INSERT INTO messages ...")
        conn.execute("UPDATE sessions SET message_count ...")
        conn.commit()
        return cur.lastrowid
```

## 修改文件

| 文件 | 修改内容 |
|------|----------|
| `merco/memory/session_store.py` | + 重试机制、+ 备份恢复、+ 完整性检查 |
| `merco/core/agent.py` | 压缩前调用备份 |
| `merco/core/session.py` | 写入失败处理 |

## 测试计划

1. 单元测试：重试机制（模拟 sqlite3.OperationalError）
2. 单元测试：完整性检查
3. 集成测试：压缩前备份/恢复
4. 手动测试：磁盘满场景（mock）

## 风险

| 风险 | 缓解 |
|------|------|
| 备份文件本身损坏 | 保留最近 N 份备份（可选） |
| 恢复后数据仍不完整 | 记录日志，提示用户 |
| 性能影响（启动检查） | 只检查不通过时再做完整校验 |