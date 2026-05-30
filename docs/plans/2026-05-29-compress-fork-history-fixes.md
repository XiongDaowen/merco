# 压缩/Fork/历史 三合一修复 实现计划

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** 修复 fork 累计虚高、压缩后历史不可见、重启压缩失效三个问题。

**Architecture:** config flag 控制 fork 行为 + /history 读 DB 展示完整消息 + metadata checkpoint 持久化压缩状态。

**Tech Stack:** Python 3.12+, SQLite, typer, rich

---

### Task 1: fork_reset_observer 可配置

**Objective:** 加配置项，fork 时根据配置决定是否清零累计。

**Files:** `merco/core/config.py`, `cli/main.py`

**Step 1: 加配置**

```python
# config.py — MercoConfig 加字段
fork_reset_observer: bool = False  # 默认不清零，继承累计
```

`_to_dict` 的 `session` 块加 `"fork_reset_observer"`，`_from_dict` 对应读取。

**Step 2: 测试**

```python
# tests/unit/test_config.py
def test_fork_reset_observer_default():
    cfg = MercoConfig()
    assert cfg.fork_reset_observer is False

def test_fork_reset_observer_from_dict():
    cfg = MercoConfig._from_dict({"session": {"fork_reset_observer": True}})
    assert cfg.fork_reset_observer is True
```

**Step 3: /fork 命令改造**

```python
# cli/main.py — /fork handler 里 observer.reset() 处改为：
agent.observer.reset(full=self.config.fork_reset_observer)  # 原来只有 reset()
```

**Step 4: Commit**

```bash
git commit -m "feat: configurable fork_reset_observer"
```

---

### Task 2: /history 从 DB 读完整消息

**Objective:** 重写 `/history` 命令，从 SessionStore 读当前会话消息（而非 sandbox snapshot）。支持分页。

**Files:** `cli/main.py`

**Step 1: 替换 /history handler**

```python
elif command == "/history":
    # 分页：/history 10 或 /history 1 10 (offset limit)
    arg = parts[1] if len(parts) > 1 else ""
    try:
        args = [int(x) for x in arg.split()]
    except ValueError:
        args = []
    offset = args[0] if len(args) >= 1 else 1
    limit = args[1] if len(args) >= 2 else 20
    
    session_data = agent._session_store.load_session(agent.session.id)
    msgs = session_data.get("messages", []) if session_data else []
    
    if not msgs:
        console.print("[dim]当前会话无消息[/dim]")
        return True
    
    total = len(msgs)
    page = msgs[offset-1:offset-1+limit]
    
    console.print(f"[bold]📋 会话 {agent.session.title or agent.session.id[:8]}"
                  f" ({offset}-{min(offset+limit-1, total)}/{total}):[/bold]")
    for i, m in enumerate(page, offset):
        role_icon = {"user": "👤", "assistant": "🤖", "tool": "🔧", "system": "⚙️"}.get(m["role"], "❓")
        content = (m.get("content") or "")[:120].replace("\n", " ")
        timestamp = m.get("timestamp", "")[:16]
        console.print(f"  {i:3d}. {role_icon} [dim]{timestamp}[/dim] {content}")
    
    if offset + limit <= total:
        console.print(f"  [dim]... 共 {total} 条。下一页: /history {offset+limit}[/dim]")
    return True
```

**Step 2: 删除旧的 /history（sandbox snapshot 版本），保留 /revert 不动**

**Step 3: 更新 /help 描述：** `/history - 查看当前会话完整消息记录`

**Step 4: 压缩后自动提示**

在 `_compress_context()` 末尾 console.print 后追加提示：
```python
console.print("[dim]→ 用 /history 查看完整记录[/dim]")
```

**Step 5: Commit**

```bash
git commit -m "feat: /history reads full messages from DB with pagination"
```

---

### Task 3: 压缩 checkpoint 持久化

**Objective:** 压缩后把摘要状态存到 metadata，重启时直接恢复压缩版，避免浪费 LLM 调用 + 重复 auto-fork。

**Files:** `merco/core/agent.py`

**Step 1: _compress_context 存 checkpoint**

压缩成功后，在 metadata 存：
```python
self.session.metadata["compress_checkpoint"] = {
    "summary": summary_text,           # LLM 生成的摘要文本
    "compressed_at": time.time(),
    "original_count": len(original_messages),  # 压缩前消息总数
    "tail_count": len(tail),           # 保留的尾巴消息数
}
```

需要改造 `_compress_context`：在调用 `compressor.compress()` 时拿到 summary 文本。当前 `llm_summary` 已经生成了摘要，传回来存一下。

**Step 2: _restore_context 检查 checkpoint**

```python
def _restore_context(self):
    self.context = ContextManager(max_tokens=self.config.max_input_tokens)
    
    checkpoint = self.session.metadata.get("compress_checkpoint")
    if checkpoint:
        # 有 checkpoint：用摘要 + 尾巴，不用全量
        summary_text = checkpoint["summary"]
        tail_count = checkpoint.get("tail_count", 6)
        all_msgs = self.session.messages
        tail = all_msgs[-tail_count:] if len(all_msgs) > tail_count else all_msgs
        
        # 注入摘要
        self.context.add({"role": "system", "content": f"[上下文已压缩] {summary_text}"})
        for msg in tail:
            self.context.add(...)  # same pattern as original
        return
    
    # 无 checkpoint：全量加载（原逻辑）
    for msg in self.session.messages:
        ...
```

**Step 3: 压缩提示加 "重启保留"**

```python
console.print("[dim]→ Context compressed (LLM summarized) — 重启后保留[/dim]")
```

**Step 4: 测试**

```python
# tests/core/test_agent.py
def test_compress_checkpoint_stored(agent):
    # trigger compress
    # verify metadata["compress_checkpoint"] exists with summary/compressed_at/original_count/tail_count

def test_restore_with_checkpoint_skips_full_load(agent):
    # set metadata compress_checkpoint
    # call _restore_context
    # verify only tail + summary loaded, not all messages
```

**Step 5: Commit**

```bash
git commit -m "feat: persist compression checkpoint in metadata for restart recovery"
```

---

## Task Order

```
Task 1: fork_reset_observer     ← 无依赖
Task 2: /history from DB        ← 无依赖
Task 3: compress checkpoint     ← 无依赖（可并行）
```

三个任务互相独立，可以一次并行派发。
