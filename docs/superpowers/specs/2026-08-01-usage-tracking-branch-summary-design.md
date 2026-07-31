# 用量追踪 + fork 分支摘要 设计

> 日期：2026-08-01
> 来源：Pi 源码级对比（`docs/user_pasted_clipboard_long_content_as_file_# Merco 查缺补漏：从 Pi 借鉴.txt` 评审 + Pi 全量分析）
> 范围：差距报告中的两个 P0 项——成本/用量追踪、会话 fork 分支摘要。

## 1. 背景与目标

Pi 在每条 assistant 消息上挂 `usage`（含 cache 细分），并聚合到会话级物化状态，使历史会话可被成本化、压缩后统计不丢。Merco 当前只在内存 `Observer` 里计 token，不落库，历史会话重开后无用量数据。

Pi 在 fork/切换分支时生成结构化分支摘要并注入目标 context，避免"切到另一条路后模型不知道发生过什么"。Merco 的 `/fork` 只全量克隆消息、`/sessions` 切换只重载历史，长会话被压缩后早期上下文丢失，切回时缺少整体定位。

**目标**：

1. 把 LLM `usage`（tokens_in / tokens_out / cached）持久化到消息行，并在会话级聚合；成本计算留给插件（Merco 不内置价格表）。
2. 在 fork 与会话切换两个时机生成分支摘要，注入 context 作为定位，复用同一摘要管线。

## 2. 范围

**做**：

- `messages` 表加 `usage` 列；`sessions` 表加 `total_tokens_in/out/cached` 聚合列。
- assistant 消息落库时携带 usage；读取/克隆/列表透传 usage 与聚合列。
- `/report` 增加本次会话 token 行（读 DB 聚合列，跨压缩历史不变）。
- `agent._summarize_branch()`：总结当前会话全部消息，写入指定 session 的 `metadata["context_summary"]`。
- `_restore_context` 在重建 context 后注入 `context_summary`（首条 system 消息）。
- `/fork` 与 `/sessions` 切换两个触发点复用同一管线。

**不做（显式排除）**：

- 价格表、成本字段、per-provider 成本——插件职责。
- 压缩摘要结构化（`_compress_context` 的 `_llm_summary` 改造）——P2 独立项。
- 会话树导航（Pi 的 `/tree` 跨分支跳转 + 摘要）——Merco 会话模型不同（每个 fork 是独立 session），本次只覆盖 fork 与 switch。
- 观测面板/成本 UI。

## 3. 设计 A：用量追踪

### 3.1 数据模型（`merco/memory/session_store.py`）

`messages` 表新增列：

```sql
usage TEXT DEFAULT '{}'   -- JSON: {tokens_in, tokens_out, cached_tokens}
```

`sessions` 表新增聚合列：

```sql
total_tokens_in    INTEGER DEFAULT 0
total_tokens_out   INTEGER DEFAULT 0
total_cached_tokens INTEGER DEFAULT 0
```

迁移沿用现有 `ALTER TABLE ... except: pass` 模式（见 `session_store.py:62-66` 的 `metadata` 列迁移）。三条新列各一个 `try/except` 块。

### 3.2 数据流

1. **捕获**（`merco/core/agent.py`）：在加 assistant 消息处把 `response.get("usage")` 传入。两处：
   - exit 路径（`agent.py:627` 的 `add_message("assistant", content)`）——`response` 在作用域内。
   - 工具调度路径（`_dispatch_tool_calls`，`agent.py:703`）——`response` 已作为参数传入。
2. **透传**（`merco/core/session.py`）：`add_message(..., usage=None)` 存到消息 dict；`save()` 把 usage 传给 `save_message(..., usage=usage)`。
3. **落库**（`session_store.py`）：`save_message` 增加 `usage` 参数；写入 `usage` 列；若 usage 非空，同事务增量累加 `sessions` 的三个聚合列（与 `message_count` 累加同处）。
4. **回读**：`load_session`、`clone_session`、`list_sessions` 透传 usage 与聚合列。`clone_session` 复制消息时带上 usage；新 session 的聚合列由复制后的消息重算（复用现有 `message_count` 重算模式，`session_store.py:337-340`）。

### 3.3 usage 结构

统一 `usage` 为 `{"tokens_in": int, "tokens_out": int, "cached_tokens": int}`。来源映射（`agent.py:569-588` 已有）：

- `tokens_in` = `usage.prompt_tokens`（fallback `context.total_tokens`）
- `tokens_out` = `usage.completion_tokens`（fallback 估算）
- `cached_tokens` = `usage.cached_tokens` 或 `usage.cache_read_tokens`

非 assistant 消息（user/tool/system）usage 为空，不累加聚合列。

### 3.4 展示（`cli/commands.py` `/report`）

`/report` 增加一行"本次会话 token"：读 `sessions` 表聚合列（`load_session` 已带回）。跨压缩历史不变（聚合列独立于 context 压缩）。

格式示例：

```
       本次会话: 入 12.3K tokens  出 4.5K tokens  68% 缓存命中
```

`/sessions` 列表可选追加 token 总量（轻量，本次先不加，留待后续）。

## 4. 设计 B：fork 分支摘要

### 4.1 摘要管线（`merco/core/agent.py`）

新增 `async def _summarize_branch(self) -> str`：

- 输入：`self.session.messages`（当前会话全部消息）。
- 门槛：消息数 < `config.session_summarize_min_messages`（默认 8）则返回 `""`，不生成空摘要。
- 构造：逐条序列化为 `[role]: content`，tool 消息截断 200 字、其余截断 600 字（复用 `_llm_summary` 的截断策略，`agent.py:888-890`）；取全部消息但设上限行数（默认 60）防止超长。
- prompt：要求生成「目标 / 进展 / 关键决策 / 下一步」的紧凑摘要（≤300 字）。这是**新管线**，独立于压缩用的 `_llm_summary`；压缩摘要结构化属 P2，不在本次范围。
- 调用：`self.provider.chat([{"role": "user", "content": prompt}], tools=[])`，与 `_llm_summary` 一致。
- 失败护栏：LLM 异常 -> 记 debug 日志，返回 `""`，不影响 fork/switch 主流程。
- 返回摘要字符串。

### 4.2 存储

写入目标 session 的 `metadata["context_summary"]`，并 `save_metadata`。每次离开时覆盖（摘要反映离开时的最新状态）。

### 4.3 注入（`merco/core/agent.py` `_restore_context`）

在 `_restore_context` 开头（创建 `ContextManager` 之后、checkpoint/消息重建之前），若 `session.metadata.get("context_summary")` 非空，作为首条 system 消息注入：

```python
summary = self.session.metadata.get("context_summary")
if summary:
    self.context.add({"role": "system", "content": summary})
```

与 `compress_checkpoint` 共存：分支摘要 = 整条会话定位；checkpoint = 压缩前缀摘要。两者作用域不同，同时存在不冲突（分支摘要在前）。

### 4.4 两个触发点

**`/fork`（`cli/commands.py:187`）**：

1. fork 前 `agent.observer.save()` + `save_metadata`（现有逻辑）。
2. `new_session = Session.fork(...)`（克隆，现有逻辑）。
3. **新增**：`summary = await agent._summarize_branch()`；若非空，写入 `new_session.metadata["context_summary"]` 并 `save_metadata(new_session.id, ...)`。摘要内容来自当前会话，写入新 fork——让 fork 启动时知道"从哪里分叉、当时进展"。
4. `agent.session = new_session` + `_restore_context()`（注入摘要，现有逻辑）。

**`/sessions` 切换（`cli/commands.py:131` 的 switch 分支）**：

1. 切换前 `agent.observer.save()` + `save_metadata`（现有逻辑）。
2. **新增**：`summary = await agent._summarize_branch()`；若非空，写入**当前（被离开的）会话** `metadata["context_summary"]` 并 `save_metadata`。下次切回该会话时注入。
3. `Session.load(target_id, ...)` + `_restore_context()`（目标会话注入它自己的摘要，现有逻辑）。

两个触发点共用 `_summarize_branch()`，差别仅在摘要写入哪个 session。

### 4.5 配置（`merco/core/config.py`）

`MercoConfig` 新增（归入 `session` 子组）：

- `session_summarize: bool = True`——总开关。`/fork` 与 `/sessions` 切换前都检查。
- `session_summarize_min_messages: int = 8`——低于此数不总结。

`_to_dict` / `_from_dict` 增加对应字段（`session` 子组，与 `fork_enabled` 等并列）。

## 5. 改动文件清单

| 文件 | 改动 |
|------|------|
| `merco/memory/session_store.py` | +`usage` 列、+3 聚合列、迁移、`save_message`+usage、`load_session`/`clone_session`/`list_sessions` 透传 |
| `merco/core/session.py` | `add_message`/`save` 透传 usage |
| `merco/core/agent.py` | 两处 assistant 消息挂 usage；`_summarize_branch()`；`_restore_context` 注入摘要 |
| `cli/commands.py` | `/fork`、`/sessions` 切换加摘要触发；`/report` 加 token 行 |
| `merco/core/config.py` | `session_summarize`、`session_summarize_min_messages` + 序列化 |
| `tests/` | session_store usage 落库/聚合、clone 透传、`_summarize_branch` 门槛与失败护栏、`_restore_context` 注入 |

## 6. 测试策略

- **SessionStore**：存带 usage 的 assistant 消息 -> 聚合列正确递增；非 assistant 消息不累加；`load_session` 回读 usage；`clone_session` 复制 usage 且新会话聚合列正确；旧库（无新列）迁移后可用。
- **`_summarize_branch`**：消息数 < 阈值返回 `""`；LLM 抛异常返回 `""` 不影响调用方；正常返回非空字符串。用 faux provider（不耗真实 token）。
- **`_restore_context`**：有 `context_summary` 时首条为 system 摘要；无则不注入；与 `compress_checkpoint` 同时存在时两者都在、摘要在前。
- **触发点**：`/fork` 摘要写入新 session；`/sessions` 切换摘要写入被离开 session。用 faux provider 验证摘要生成调用与落库。
- 运行方式：`uv run pytest`（见记忆：`.venv` shim 失效，用 `uv run`）。

## 7. 向后兼容

- DB 迁移用 `ALTER TABLE ... except: pass`，旧库自动加列，默认值保证旧消息 usage 为空、聚合列为 0。
- `add_message`/`save_message` 的 usage 参数默认 `None`，现有调用方不传也不报错。
- `session_summarize` 默认 `True`，但失败护栏保证摘要出错时不影响 fork/switch 主流程。
- 现有插件不受影响：usage 是消息 dict 上的可选字段，`context_summary` 是 metadata 上的可选键。
