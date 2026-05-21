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
