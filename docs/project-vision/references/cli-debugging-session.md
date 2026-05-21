# 开发会话记录: Phase 1 CLI 调试

> 2026-05-20 | 首次 CLI 实测，修 4 个 bug

## Bug 清单

### 1. 工具调用 400: tool 消息前无 tool_calls

**根因**: `_agent_loop` 执行工具前，没有写入 `assistant(tool_calls)` 消息。消息序列变成 `system → user → tool`，Qwen3 严格校验顺序拒绝。

**修复**: `agent.py` — 工具执行前先写入 `assistant(tool_calls)` 消息。

### 2. 终端输出 surrogates 导致 400

**根因**: `bash` 输出含非 UTF-8 字节，`decode()` 默认严格模式产生代理对字符（surrogates），`json.dumps` 序列化时炸掉，OpenAI 兼容 API 拒绝。

**修复**:
- `bash_tools.py` — `decode("utf-8", errors="replace")`
- `agent.py` — `json.dumps(ensure_ascii=True)`
- `llm.py` — 发 API 前用 `_clean_surrogates()` 递归过滤所有消息

### 3. 429 限流 + 请求放大 6 倍

**根因**: `AsyncOpenAI` 默认自带 2 次重试，Agent 层又加了 3 次。1 次原始请求 + SDK 重试 2 次 + Agent 重试 3 次 = 最多 6 次。scnet 免费额度迅速打满。

**修复**:
- `llm.py` — `max_retries=0` 关闭 SDK 重试，由 Agent 层统一控制
- `agent.py` — 仅对 429/5xx 重试，400 类错误直接抛出
- `agent.py` — 工具执行后 `asyncio.sleep(0.5)` 防突发限制

### 4. Ctrl+C 退出卡顿

**根因**: `run_in_executor` 阻塞 `input()` 线程，Ctrl+C 信号先到主线程但 executor 线程仍在等输入。`agent.run()` 执行中无法中断。

**修复**:
- `cli/main.py` — 注册 `SIGINT`/`SIGTERM` 信号处理器，取消正在运行的 `asyncio.Task`
- `cli/main.py` — `asyncio.to_thread` 替代 `run_in_executor`，Ctrl+C 响应更快
- 两级退出：第一次取消当前操作，第二次直接退出

## 技术模式

### 重试协调原则

**SDK 自带重试 + Agent 层重试 = 请求放大**。

```python
# 正确做法：关闭 SDK 重试，Agent 层统一控制
client = AsyncOpenAI(api_key=..., max_retries=0)

# Agent 层只重试 429/5xx，不重试 4xx
if is_rate_limit or is_server_error:
    await asyncio.sleep(wait)
```

### Surrogates 防御三层

```
源头: decode("utf-8", errors="replace")  ← bash_tools.py
序列化: ensure_ascii=True               ← agent.py
发送前: _clean_surrogates(messages)      ← llm.py
```

### Asyncio REPL 信号处理

```python
loop.add_signal_handler(signal.SIGINT, handle_interrupt)
# handle_interrupt: task.cancel() + loop.stop()
```
