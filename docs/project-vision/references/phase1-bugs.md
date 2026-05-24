# OpenMercury Phase 1 Bugs & Fixes

## Bug 1: Tool call message ordering (agent.py)

**Symptom**: `Error code: 400 - messages with role "tool" must be a response to a preceeding message with "tool_calls"` (SCNet/Qwen3)

**Root cause**: `agent.py._agent_loop()` executed tools and appended `tool` messages to context, but never appended the `assistant` message that contained the `tool_calls`. The API received `system → user → tool` instead of `system → user → assistant(tool_calls) → tool`.

**Fix** (agent.py, line ~87): Before calling `_execute_tool_calls()`, append the assistant message with tool_calls to context:
```python
assistant_msg = {"role": "assistant", "content": "", "tool_calls": tool_calls}
self.context.add(assistant_msg)
```

**Lesson**: Every `tool` message MUST be preceded by the `assistant` message that initiated it. This is OpenAI API protocol, not optional. Qwen3 enforces it strictly.

---

## Bug 2: UTF-8 surrogate characters in bash output (bash_tools.py)

**Symptom**: `'utf-8' codec can't encode characters` or `surrogates not allowed` during JSON serialization of tool results.

**Root cause**: `stdout.decode()` uses strict mode. Terminal output from `ls` or other commands can contain non-UTF-8 bytes. These survive into `json.dumps()` and either crash serialization or produce invalid surrogate characters that the LLM API rejects.

**Fix** (bash_tools.py, line ~36):
```python
"stdout": stdout.decode("utf-8", errors="replace") if stdout else "",
"stderr": stderr.decode("utf-8", errors="replace") if stderr else "",
```

**Lesson**: Always use `errors="replace"` when decoding subprocess output. Never assume stdout is valid UTF-8.

---

## Bug 3: Surrogate characters in LLM messages (llm.py)

**Symptom**: `'utf-8' codec can't encode characters in position N: surrogates not allowed` when calling LLM API.

**Root cause**: Tool results or user input can contain `\ud800-\udfff` surrogate characters. These pass through Python's JSON module (`ensure_ascii=True` preserves them) but are rejected by the LLM API encoder.

**Fix** (llm.py): Added `_clean_surrogates()` helper that recursively strips surrogate characters from all message content before sending:
```python
_SURROGATE_RE = re.compile(r'[\ud800-\udfff]')

def _clean_surrogates(obj):
    if isinstance(obj, str):
        return _SURROGATE_RE.sub('', obj)
    if isinstance(obj, list):
        return [_clean_surrogates(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _clean_surrogates(v) for k, v in obj.items()}
    return obj
```

Applied in `chat()` and `chat_stream()`: `"messages": _clean_surrogates(messages)`

---

## Bug 4: No retry on API errors (agent.py)

**Symptom**: 429 rate limit or 500 server error crashes the agent loop immediately, losing the conversation.

**Root cause**: `llm.chat()` call has no error handling. Any exception propagates and kills the loop.

**Fix** (agent.py, line ~75): Added exponential backoff retry wrapper:
```python
max_retries = 3
last_error = None
for attempt in range(max_retries):
    try:
        response = await self.llm.chat(messages, tools=tools)
        break
    except Exception as e:
        last_error = e
        if attempt < max_retries - 1:
            wait = 2 ** attempt  # 2s, 4s
            console.print(f"[yellow]API error, retry in {wait}s ({attempt+1}/{max_retries-1}): {e}[/yellow]")
            await asyncio.sleep(wait)
        else:
            raise last_error
```

---

## Pattern: Provider compatibility notes

- **Qwen3 (via SCNet)** enforces strict message ordering — `tool` messages MUST follow `assistant(tool_calls)`. Not all providers are this strict, but the OpenAI spec requires it.
- **OpenAI Python SDK** doesn't filter surrogate characters from message content. Any provider using the OpenAI-compatible endpoint may reject messages with `\ud800-\udfff`.

---

## 附录: 2026-05-20 CLI 首次调试记录

首次 CLI 实测记录，与上述 Bug 1-4 重叠，保留作为调试上下文参考。

### Bug 清单

**Bug 1: 工具调用 400 — tool 消息前无 tool_calls**

*同 phase1 Bug 1。*

**Bug 2: 终端输出 surrogates 导致 400**

*同 phase1 Bug 2/3。*

**Bug 3: 429 限流 + 请求放大 6 倍**

根因: `AsyncOpenAI` 默认自带 2 次重试，Agent 层又加了 3 次。1 次原始请求 + SDK 重试 2 次 + Agent 重试 3 次 = 最多 6 次。scnet 免费额度迅速打满。

*同 phase1 Bug 4，补充根因细节。*

**Bug 4: Ctrl+C 退出卡顿**

根因: `run_in_executor` 阻塞 `input()` 线程，Ctrl+C 信号先到主线程但 executor 线程仍在等输入。`agent.run()` 执行中无法中断。

修复:
- `cli/main.py` — 注册 `SIGINT`/`SIGTERM` 信号处理器，取消正在运行的 `asyncio.Task`
- `cli/main.py` — `asyncio.to_thread` 替代 `run_in_executor`，Ctrl+C 响应更快
- 两级退出：第一次取消当前操作，第二次直接退出

### 技术模式

**重试协调原则**: SDK 自带重试 + Agent 层重试 = 请求放大。关闭 SDK 重试 (`max_retries=0`)，由 Agent 层统一控制，且仅重试 429/5xx，不重试 4xx。

**Surrogates 防御三层**:
```
源头: decode("utf-8", errors="replace")  ← bash_tools.py
序列化: ensure_ascii=True               ← agent.py
发送前: _clean_surrogates(messages)      ← llm.py
```

**Asyncio REPL 信号处理**:
```python
loop.add_signal_handler(signal.SIGINT, handle_interrupt)
# handle_interrupt: task.cancel() + loop.stop()
```
