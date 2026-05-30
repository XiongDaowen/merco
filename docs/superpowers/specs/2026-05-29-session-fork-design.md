# 会话 Fork/分支 — 设计规格

> 会话 fork：手动 `/fork` 克隆当前会话 → 独立分支。压缩自动 fork：上下文压缩前自动归档完整副本。

## 动机

merco 已有会话持久化（`SessionStore`）、父链字段（`parent_id`），但无 fork 能力。对标 hermes/opencode/opencorw 都有会话分支能力，merco 缺此项。

## 方案选择

**方案 B** — 手动 fork + 压缩自动 fork，预留会话树可视化（方案 C）架构：

- `/fork` 命令手动克隆会话
- 上下文压缩触发时自动 fork 完整副本（归档）
- SessionStore 预留 `get_children()` 接口，为 `/tree` 命令做准备

## 架构总览

```
用户 /fork →
  Session.fork(session_id) → new session
  Agent 切换到新 session

--- 或 ---

上下文压缩触发 →
  Session.fork(session_id) → 完整副本（归档）
  当前会话继续压缩后的上下文
```

## 核心组件

### 1. SessionStore.clone_session()

深克隆：复制 sessions 行 + 全量 messages → 新 session_id。

### 2. Session.fork() — 工厂方法

```python
@classmethod
def fork(cls, session_id: str, store) -> "Session":
    new_id = store.clone_session(session_id, parent_id=session_id)
    return cls.load(new_id, store)
```

### 3. Agent._compress_context 自动 fork

压缩前：`if fork_auto_on_compress → save() → fork() → 归档提示`。然后正常压缩。

### 4. CLI /fork 命令

保存当前 → fork → 切换到新会话 → 提示。

### 5. /tree 预留

`SessionStore.get_children(parent_id)` 接口 + CLI 占位命令。

## 配置项

```json
{
  "session": {
    "fork_enabled": true,
    "fork_auto_on_compress": true
  }
}
```

## 边界情况

| 场景 | 行为 |
|------|------|
| 新会话（< 2 轮）fork | 允许，提示内容较少 |
| 连续 fork | parent_id 指向直接父会话 |
| fork 的 fork | 链式 parent_id |
| 未存盘时 fork | 先 save() |
| 自动 fork 禁用 | 跳过，压缩照常 |

## 改动文件

| 文件 | 改动 |
|------|------|
| `merco/memory/session_store.py` | `clone_session()` + `get_children()` 接口预留 |
| `merco/core/session.py` | `fork()` 工厂方法 |
| `merco/core/agent.py` | `_compress_context` 插入 fork + `switch_to()` |
| `merco/core/config.py` | `session.fork_enabled` + `session.fork_auto_on_compress` |
| `cli/main.py` | `/fork` + `/tree` 占位 |

## 预留扩展

- `SessionStore.get_children(parent_id)` → 查子会话列表
- `/tree` 命令 → 展示 parent_id 树
- 浅 fork（只带 system prompt + 摘要）
- 跨分支 diff（对比两个分支的消息差异）
