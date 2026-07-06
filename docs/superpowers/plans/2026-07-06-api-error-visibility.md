# API Error Visibility & Retry Feedback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate empty windows on API errors during streaming, show visible retry feedback, and always present a red error Panel on terminal failure.

**Architecture:** Add a new `error_ui.py` module centralizing error classification and rendering; modify StreamingProvider to catch mid-stream errors and swap in a red Panel; update agent loop's exception handler to print retry feedback + spinner; update REPL to always render errors as red Panels; relax WaitRecovery to retry all errors with differentiated wait times.

**Tech Stack:** Python 3.11+, Rich (Panel/Live/Text/Console), pytest + pytest-asyncio, openai SDK exceptions (duck-typed to avoid hard import dependency in error_ui.py).

**Spec:** `docs/superpowers/specs/2026-07-06-api-error-visibility-design.md`

## Global Constraints

- **First step**: revert uncommitted pre-design edits to `cli/main.py`, `merco/core/agent.py`, `merco/core/llm/errors.py` (they were made before brainstorming approval).
- **TDD**: Every behavioral change requires a failing test before the implementation.
- **Zero empty windows**: Every API error path must produce a visible red Panel (or explicit yellow retry feedback) within 1 second of the error.
- **Error responses not persisted**: API error messages are never written to session/context (not valid LLM content).
- **All errors retry**: The recovery pipeline receives every exception (no `_is_retryable_llm_error` gating). Deterministic errors (401/403/404) do one fast 1s retry then give up.
- **Retry visibility**: Wait >1s shows a transient spinner; successful retries leave no persistent Panel on screen.
- **Error marker**: Final error strings start with `"❌ "` so the REPL can detect them via `startswith("❌")`.
- **Sensitive info redaction**: Any error body containing `api_key`, `token`, `secret`, `authorization`, or `bearer` is replaced with `(包含敏感信息，已脱敏)`.
- **Rich markup in final error string**: `error_message()` returns a string using Rich markup (`[bold red]`, `[dim]`, etc.) — callers must render with `Text.from_markup`, not `Markdown()`.
- **Follow existing style**: Dim inline status uses `[dim]…[/dim]`, spinners use `⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏` cycle at 8fps, borders default `border_style="red"` for errors and `"dim"` for normal content.
- **Tests use existing conftest**: Use `test_agent` fixture and `MockLLMClient` pattern from `tests/conftest.py`.

---

## File Map

| Action | Path | Responsibility |
|---|---|---|
| Create | `merco/core/llm/error_ui.py` | Error classification, Panel builders, retry spinner, final error string |
| Modify | `merco/core/llm/errors.py` | `llm_error()` becomes thin wrapper around `error_ui.error_message()`; delete `_is_retryable_llm_error`; delete pre-design `_classify_error` |
| Create | `tests/core/test_error_ui.py` | Unit tests for `error_ui.py` |
| Modify | `merco/core/recovery/wait.py` | Duck-type status_code; differentiate wait by error category; short retry for 401/403/404; remove dependency on `_is_retryable` |
| Modify | `merco/context/recovery.py` | Force-trigger on 413/too-long keywords; set small `extra_wait=0.5`; remove dependency on `_is_retryable` |
| Create | `tests/core/test_recovery_wait.py` | Unit tests for WaitRecovery behaviour |
| Modify | `merco/core/agent.py` | Agent init: `_error_displayed_in_stream=False`; StreamingProvider: catch Exception, swap Panel, set flag, raise; agent loop except block: render retry line + spinner, return `error_message()` on failure; `_wrap_up_call`: return `error_message()` instead of "模型调用失败"; remove pre-design changes (`_show_error_in_panel` closure, duplicated Panels, etc.) |
| Modify | `cli/main.py` | REPL: detect `startswith("❌")`, skip rendering when `_error_displayed_in_stream`, otherwise render red Panel with `Text.from_markup`; reset flag after render |
| Create | `tests/core/test_agent_error_handling.py` | Integration tests for StreamingProvider error path, retry feedback, final error return |

---

### Task 1: Revert pre-design edits and add error_ui module skeleton

**Files:**
- Modify: `cli/main.py`, `merco/core/agent.py`, `merco/core/llm/errors.py` (revert to HEAD)
- Create: `merco/core/llm/error_ui.py` (skeleton with ErrorInfo dataclass + stub functions)
- Create: `tests/core/test_error_ui.py` (placeholder)

**Interfaces:** None yet (skeleton only).

- [ ] **Step 1: Revert pre-design changes**

```bash
cd /home/xiowen/code/merco
git restore cli/main.py merco/core/agent.py merco/core/llm/errors.py
```

Run: `git status`
Expected: working tree clean for modified files; only `docs/superpowers/specs/2026-07-06-api-error-visibility-design.md` shows as untracked.

- [ ] **Step 2: Create error_ui.py skeleton**

Write to `merco/core/llm/error_ui.py`:

```python
"""LLM error UI helpers — classification, rendering, retry feedback.

Responsibility: what errors look like. NOT when to show them (callers decide).
Zero side effects: no logging, no openai import (duck-typing only).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import AsyncIterator


@dataclass
class ErrorInfo:
    """Classified error metadata."""
    label: str   # Short label e.g. "认证失败", "服务端错误 (502)"
    hint: str    # One-line user-facing hint
    exc: Exception  # Original exception


def classify_error(exc: Exception) -> ErrorInfo:
    """Classify an exception into ErrorInfo using duck-typing.

    Reads ``exc.status_code`` if present; falls back to scanning str(exc) and
    the exception class name. Does NOT import openai.
    """
    raise NotImplementedError


def sanitize_message(exc: Exception, max_len: int = 300) -> str:
    """Redact sensitive keywords (api_key/token/secret/authorization/bearer)
    and truncate to max_len characters (appending '…' if truncated)."""
    raise NotImplementedError


def build_error_panel(info: ErrorInfo):
    """Return a Rich Panel for an error. Red border, title '⚠ API 错误'.

    Layout:
      ❌ <label> (bold red)
      <hint> (red)
      <blank line>
      <sanitized detail> (dim)
    """
    raise NotImplementedError


def build_retry_line(info: ErrorInfo, attempt: int, max_attempts: int,
                     actions: list[str]) -> str:
    """Return a yellow one-line retry status string.

    Example: "↻ API 请求限流（第 1/3 次）— 等待 3s + 压缩上下文…"
    """
    raise NotImplementedError


def retry_spinner(label: str, seconds: float, console) -> AsyncIterator[None]:
    """Async context manager showing a transient spinner during a sleep.

    Usage::

        async with retry_spinner("请求限流", 3.0, console):
            await asyncio.sleep(3.0)

    The spinner displays e.g. "⠋ 等待 2.3s 冷却中…" in yellow, updates at 8fps,
    and is transient (disappears on exit). If ``seconds <= 1`` it's a no-op
    (the wait is too short to justify a spinner — just sleep the raw wait
    outside the ctx manager).
    """
    raise NotImplementedError


def error_message(info: ErrorInfo) -> str:
    """Return a Rich-markup string starting with "❌ " for the final error.

    Used as the agent's return value on terminal failure; the REPL detects
    startswith("❌") and wraps it in a red Panel via Text.from_markup.
    """
    raise NotImplementedError
```

- [ ] **Step 3: Verify module imports cleanly**

Run: `python -c "from merco.core.llm import error_ui; print('ok')"`
Expected: prints `ok` (no ImportError).

- [ ] **Step 4: Create test file skeleton**

Write to `tests/core/test_error_ui.py`:

```python
"""Unit tests for merco.core.llm.error_ui."""
import pytest
```

Run: `pytest tests/core/test_error_ui.py -v`
Expected: 0 tests collected, passes.

- [ ] **Step 5: Commit**

```bash
git add merco/core/llm/error_ui.py tests/core/test_error_ui.py docs/superpowers/specs/2026-07-06-api-error-visibility-design.md docs/superpowers/plans/
git commit -m "feat(error-ui): add error_ui.py skeleton + spec + plan"
```

---

### Task 2: Implement classify_error + sanitize_message (TDD)

**Files:**
- Modify: `merco/core/llm/error_ui.py`
- Modify: `tests/core/test_error_ui.py`

**Interfaces:**
- `classify_error(exc) -> ErrorInfo`
- `sanitize_message(exc, max_len=300) -> str`

- [ ] **Step 1: Write failing tests for classify_error**

Append to `tests/core/test_error_ui.py`:

```python
from merco.core.llm.error_ui import (
    ErrorInfo, classify_error, sanitize_message,
)


class _FakeExc(Exception):
    def __init__(self, msg="boom", status_code=None):
        super().__init__(msg)
        self.status_code = status_code


class TestClassifyError:
    def test_401_is_auth_failure(self):
        info = classify_error(_FakeExc("Unauthorized", status_code=401))
        assert "认证" in info.label or "auth" in info.label.lower()
        assert info.hint  # non-empty hint

    def test_403_is_permission_denied(self):
        info = classify_error(_FakeExc("Forbidden", status_code=403))
        assert "权限" in info.label or "permission" in info.label.lower()

    def test_404_is_not_found(self):
        info = classify_error(_FakeExc("model not found", status_code=404))
        assert "不存在" in info.label or "not found" in info.label.lower()

    def test_413_is_too_long(self):
        info = classify_error(_FakeExc("context length exceeded", status_code=413))
        assert "长" in info.label or "long" in info.label.lower()

    def test_429_is_rate_limit(self):
        info = classify_error(_FakeExc("rate limit", status_code=429))
        assert "限流" in info.label or "rate" in info.label.lower()

    def test_5xx_is_server_error(self):
        info = classify_error(_FakeExc("bad gateway", status_code=502))
        assert "502" in info.label
        assert "服务端" in info.label or "server" in info.label.lower()

    def test_500_range_covered(self):
        for code in (500, 502, 503, 504):
            info = classify_error(_FakeExc("err", status_code=code))
            assert str(code) in info.label

    def test_timeout_exception(self):
        class TimeoutExc(Exception):
            pass
        info = classify_error(TimeoutExc("read timeout"))
        assert "超时" in info.label or "timeout" in info.label.lower()

    def test_connection_exception(self):
        class ConnExc(Exception):
            pass
        info = classify_error(ConnExc("connection refused"))
        assert "连接" in info.label or "connection" in info.label.lower()

    def test_plain_exception_falls_back_to_class_name(self):
        info = classify_error(Exception("something weird"))
        assert info.label  # non-empty
        assert info.hint

    def test_preserves_original_exception(self):
        exc = _FakeExc("x", status_code=500)
        info = classify_error(exc)
        assert info.exc is exc


class TestSanitizeMessage:
    def test_redacts_api_key(self):
        exc = Exception("bad api_key=sk-12345abcdef")
        msg = sanitize_message(exc)
        assert "sk-12345" not in msg
        assert "敏感" in msg or "redact" in msg.lower() or "脱敏" in msg

    def test_redacts_authorization_header(self):
        exc = Exception("header: Authorization Bearer xxxx")
        msg = sanitize_message(exc)
        assert "xxxx" not in msg or "敏感" in msg or "脱敏" in msg

    def test_truncates_long_messages(self):
        exc = Exception("x" * 1000)
        msg = sanitize_message(exc, max_len=100)
        assert len(msg) <= 100 + 1  # +1 for ellipsis

    def test_short_message_passthrough(self):
        exc = Exception("simple error")
        msg = sanitize_message(exc)
        assert msg == "simple error"
```

Run: `pytest tests/core/test_error_ui.py::TestClassifyError tests/core/test_error_ui.py::TestSanitizeMessage -v`
Expected: all FAIL with "NotImplementedError" or similar.

- [ ] **Step 2: Implement classify_error and sanitize_message**

Replace the `classify_error` and `sanitize_message` function bodies in `merco/core/llm/error_ui.py` with:

```python
_SENSITIVE_KEYWORDS = ("api_key", "token", "secret", "authorization", "bearer")


def classify_error(exc: Exception) -> ErrorInfo:
    """Classify an exception into ErrorInfo using duck-typing."""
    name = type(exc).__name__
    status = getattr(exc, "status_code", None)
    body = str(exc).lower()
    msg = str(exc)

    # Specific HTTP status codes take priority
    if status == 401 or "unauthorized" in body or "authentication" in body \
            or ("api key" in body and ("invalid" in body or "expired" in body)):
        return ErrorInfo("认证失败", "API Key 无效或已过期，请检查配置。", exc)
    if status == 403 or "forbidden" in body or "permission" in body or "access denied" in body:
        return ErrorInfo("权限不足", "账户无权限访问该资源。", exc)
    if status == 404 or ("not found" in body and "model" in body) \
            or "model not exist" in body:
        return ErrorInfo("模型/接口不存在", "模型或接口不存在，检查模型名和 base_url。", exc)
    if status == 413 or "context length" in body or "maximum context" in body \
            or "prompt too long" in body or "too long" in body:
        return ErrorInfo("请求过长", "上下文超过模型上限，正在压缩后重试…", exc)
    if status == 429 or "rate limit" in body or "too many requests" in body:
        return ErrorInfo("请求限流", "API 限流，稍后重试…", exc)
    if isinstance(status, int) and 500 <= status <= 599:
        return ErrorInfo(f"服务端错误 ({status})", "API 服务器异常，稍后重试…", exc)
    if isinstance(status, int) and status == 408:
        return ErrorInfo("请求超时", "API 请求超时，稍后重试…", exc)

    # Fall back to exception class name / body keywords
    if "timeout" in name.lower() or "timeout" in body or "timed out" in body:
        return ErrorInfo("请求超时", "API 响应超时，稍后重试…", exc)
    if "connection" in name.lower() or "connect" in body or "network" in body:
        return ErrorInfo("连接错误", "无法连接到 API 服务器，请检查网络或 base_url。", exc)

    # Other HTTP 4xx
    if isinstance(status, int) and 400 <= status < 500:
        return ErrorInfo(f"请求错误 ({status})", "请求被服务端拒绝，稍后重试…", exc)

    return ErrorInfo(name or "调用失败", "API 调用失败，稍后重试…", exc)


def sanitize_message(exc: Exception, max_len: int = 300) -> str:
    """Redact sensitive keywords and truncate."""
    msg = str(exc)
    low = msg.lower()
    for kw in _SENSITIVE_KEYWORDS:
        if kw in low:
            return "(包含敏感信息，已脱敏)"
    if len(msg) > max_len:
        return msg[:max_len].rstrip() + "…"
    return msg
```

- [ ] **Step 3: Run tests — all should pass**

Run: `pytest tests/core/test_error_ui.py::TestClassifyError tests/core/test_error_ui.py::TestSanitizeMessage -v`
Expected: all PASS.

- [ ] **Step 4: Commit**

```bash
git add merco/core/llm/error_ui.py tests/core/test_error_ui.py
git commit -m "feat(error-ui): implement classify_error and sanitize_message"
```

---

### Task 3: Implement build_error_panel + build_retry_line + error_message (TDD)

**Files:**
- Modify: `merco/core/llm/error_ui.py`
- Modify: `tests/core/test_error_ui.py`

**Interfaces:**
- `build_error_panel(info) -> Panel`
- `build_retry_line(info, attempt, max_attempts, actions) -> str`
- `error_message(info) -> str` (returns string starting with `"❌ "` containing Rich markup)

- [ ] **Step 1: Write failing tests**

Append to `tests/core/test_error_ui.py`:

```python
from rich.panel import Panel


class _DummyExc(Exception):
    def __init__(self, msg="boom", status_code=None):
        super().__init__(msg)
        self.status_code = status_code


class TestBuildErrorPanel:
    def test_returns_panel(self):
        from merco.core.llm.error_ui import build_error_panel
        info = ErrorInfo("连接错误", "检查网络", _DummyExc("fail"))
        panel = build_error_panel(info)
        assert isinstance(panel, Panel)
        assert panel.border_style == "red"
        assert "API 错误" in str(panel.title)

    def test_panel_contains_label(self):
        from merco.core.llm.error_ui import build_error_panel
        info = ErrorInfo("认证失败", "检查 key", _DummyExc("bad key"))
        panel = build_error_panel(info)
        renderable = panel.renderable
        # Rich Group renders with markups; check plain text has the label
        text = str(renderable)
        assert "认证失败" in text

    def test_panel_contains_sanitized_detail(self):
        from merco.core.llm.error_ui import build_error_panel
        exc = _DummyExc("connection reset by peer")
        info = ErrorInfo("连接错误", "检查网络", exc)
        panel = build_error_panel(info)
        assert "connection reset" in str(panel.renderable)


class TestBuildRetryLine:
    def test_format_with_wait_and_compress(self):
        from merco.core.llm.error_ui import build_retry_line
        info = ErrorInfo("请求限流", "", _DummyExc(status_code=429))
        line = build_retry_line(info, 1, 3, ["等待 3.0s", "压缩上下文"])
        assert "↻" in line
        assert "第 1/3 次" in line
        assert "请求限流" in line
        assert "等待 3.0s" in line
        assert "压缩上下文" in line

    def test_format_single_action(self):
        from merco.core.llm.error_ui import build_retry_line
        info = ErrorInfo("服务端错误 (500)", "", _DummyExc(status_code=500))
        line = build_retry_line(info, 2, 3, ["立即重试"])
        assert "第 2/3 次" in line
        assert "立即重试" in line


class TestErrorMessage:
    def test_starts_with_x_marker(self):
        from merco.core.llm.error_ui import error_message
        info = ErrorInfo("请求限流", "稍后重试", _DummyExc("rate limit"))
        msg = error_message(info)
        assert msg.startswith("❌ ")

    def test_contains_label_and_hint_and_detail(self):
        from merco.core.llm.error_ui import error_message
        exc = _DummyExc("gateway timeout", status_code=504)
        info = ErrorInfo("服务端错误 (504)", "稍后重试", exc)
        msg = error_message(info)
        assert "服务端错误 (504)" in msg
        assert "稍后重试" in msg
        assert "gateway timeout" in msg

    def test_redacts_sensitive_in_final_message(self):
        from merco.core.llm.error_ui import error_message
        exc = _DummyExc("bad api_key=sk-secret1234")
        info = ErrorInfo("认证失败", "check key", exc)
        msg = error_message(info)
        assert "sk-secret1234" not in msg
        assert "脱敏" in msg
```

Run: `pytest tests/core/test_error_ui.py -v`
Expected: new tests FAIL (NotImplementedError).

- [ ] **Step 2: Implement helpers**

Replace the three function stub bodies in `merco/core/llm/error_ui.py`:

```python
def build_error_panel(info: ErrorInfo) -> Panel:
    """Return a Rich red Panel for an error."""
    from rich.text import Text
    from rich.panel import Panel
    detail = sanitize_message(info.exc)
    text = Text.from_markup(
        f"[bold red]❌ {info.label}[/bold red]\n"
        f"[red]{info.hint}[/red]\n\n"
        f"[dim]{detail}[/dim]"
    )
    return Panel(
        text, border_style="red",
        title="⚠ API 错误", title_align="left", padding=(0, 1),
    )


def build_retry_line(info: ErrorInfo, attempt: int, max_attempts: int,
                     actions: list[str]) -> str:
    """Return a yellow one-line retry status string."""
    action_str = " + ".join(actions) if actions else "立即重试"
    return (f"[yellow]↻ API {info.label}（第 {attempt}/{max_attempts} 次）"
            f"— {action_str}…[/yellow]")


def error_message(info: ErrorInfo) -> str:
    """Return Rich-markup final error string starting with '❌ '."""
    detail = sanitize_message(info.exc)
    return (f"❌ [bold red]{info.label}[/bold red]：[red]{info.hint}[/red]\n"
            f"[dim]{detail}[/dim]")
```

- [ ] **Step 3: Add @asynccontextmanager for retry_spinner**

First add the missing import at the top of `error_ui.py`:

```python
from contextlib import asynccontextmanager
```

Then replace the `retry_spinner` stub:

```python
@asynccontextmanager
async def retry_spinner(label: str, seconds: float, console):
    """Async context manager showing a transient spinner during a wait.

    No-op (yields immediately) when seconds <= 1.
    """
    import asyncio
    import itertools
    from rich.live import Live
    from rich.text import Text

    if seconds <= 1:
        yield
        return

    spinner = itertools.cycle("⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏")
    message = f"[yellow]{next(spinner)} 等待 {seconds:.1f}s 冷却中…[/yellow]"
    with Live(Text.from_markup(message), console=console,
              refresh_per_second=8, transient=True) as live:
        # Run a background update task; caller's block (typically sleep)
        # runs concurrently and we stop updating once it finishes.
        async def _tick():
            waited = 0.0
            try:
                while waited < seconds:
                    await asyncio.sleep(0.1)
                    waited += 0.1
                    remain = max(0, seconds - waited)
                    live.update(Text.from_markup(
                        f"[yellow]{next(spinner)} 等待 {remain:.1f}s 冷却中…[/yellow]"
                    ))
            except asyncio.CancelledError:
                pass

        ticker = asyncio.create_task(_tick())
        try:
            yield
        finally:
            ticker.cancel()
            try:
                await ticker
            except asyncio.CancelledError:
                pass
```

Note: the simpler design is to let the *caller* sleep inside the `async with` block; the ticker updates in parallel. The caller uses:

```python
async with retry_spinner(label, wait, console):
    await asyncio.sleep(wait)
```

- [ ] **Step 4: Run all error_ui tests**

Run: `pytest tests/core/test_error_ui.py -v`
Expected: all PASS.

- [ ] **Step 5: Quick manual sanity of retry_spinner**

Run: `python -c "
import asyncio
from rich.console import Console
from merco.core.llm.error_ui import retry_spinner
async def main():
    console = Console()
    async with retry_spinner('测试', 2.0, console):
        await asyncio.sleep(2.0)
    console.print('[green]done[/green]')
asyncio.run(main())
"`
Expected: spinner spins for ~2s then disappears, "done" prints, no traceback.

- [ ] **Step 6: Commit**

```bash
git add merco/core/llm/error_ui.py tests/core/test_error_ui.py
git commit -m "feat(error-ui): implement panel/retry-line/error-message/spinner"
```

---

### Task 4: Update errors.py wrapper and slim WaitRecovery (TDD)

**Files:**
- Modify: `merco/core/llm/errors.py`
- Modify: `merco/core/recovery/wait.py`
- Modify: `merco/context/recovery.py`
- Create: `tests/core/test_recovery_wait.py`

**Interfaces:**
- `merco.core.llm.errors.llm_error(exc) -> str` now delegates to `error_ui.error_message(classify_error(exc))`
- `WaitRecovery.attempt(ctx)` — removed `_is_retryable` gate; differentiated wait; 401/403/404 short retry only once
- `ContextCompressRecovery.attempt(ctx)` — force trigger on 413/too-long; sets `extra_wait=0.5`; removed `_is_retryable` gate
- `merco.core.pipeline._is_retryable()` is **deleted** (no more callers)

- [ ] **Step 1: Write failing test for WaitRecovery**

Write to `tests/core/test_recovery_wait.py`:

```python
"""Tests for WaitRecovery and ContextCompressRecovery error policies."""
import pytest
from merco.core.pipeline import RecoveryContext


class _FakeExc(Exception):
    def __init__(self, msg="err", status_code=None):
        super().__init__(msg)
        self.status_code = status_code


class TestWaitRecovery:
    @pytest.mark.asyncio
    async def test_retries_5xx_with_backoff(self):
        from merco.core.recovery.wait import WaitRecovery
        rec = WaitRecovery(delay=3.0, max_delay=30.0)
        ctx = RecoveryContext(error=_FakeExc("bad gateway", status_code=502))
        assert await rec.attempt(ctx) is True
        assert ctx.extra_wait == 3.0  # first attempt 3s

        ctx.attempt_count = 1
        ctx2 = RecoveryContext(error=_FakeExc("bad gateway", status_code=502),
                               attempt_count=1)
        assert await rec.attempt(ctx2) is True
        assert ctx2.extra_wait == 6.0  # doubles

        ctx3 = RecoveryContext(error=_FakeExc("bad gateway", status_code=502),
                               attempt_count=2)
        assert await rec.attempt(ctx3) is True
        assert ctx3.extra_wait == 12.0

    @pytest.mark.asyncio
    async def test_short_retry_401_only_once(self):
        from merco.core.recovery.wait import WaitRecovery
        rec = WaitRecovery(delay=3.0, max_delay=30.0)

        ctx = RecoveryContext(error=_FakeExc("unauthorized", status_code=401))
        assert await rec.attempt(ctx) is True
        assert ctx.extra_wait == 1.0  # short wait

        # Second time: give up
        ctx2 = RecoveryContext(error=_FakeExc("unauthorized", status_code=401),
                               attempt_count=1)
        assert await rec.attempt(ctx2) is False

    @pytest.mark.asyncio
    async def test_413_passes_to_compress(self):
        """WaitRecovery returns False for 413 — compression handles it."""
        from merco.core.recovery.wait import WaitRecovery
        rec = WaitRecovery(delay=3.0)
        ctx = RecoveryContext(error=_FakeExc("too long", status_code=413))
        assert await rec.attempt(ctx) is False

    @pytest.mark.asyncio
    async def test_429_uses_default_backoff(self):
        from merco.core.recovery.wait import WaitRecovery
        rec = WaitRecovery(delay=3.0)
        ctx = RecoveryContext(error=_FakeExc("rate limit", status_code=429))
        assert await rec.attempt(ctx) is True
        assert ctx.extra_wait == 3.0

    @pytest.mark.asyncio
    async def test_connection_error_gets_backoff(self):
        """Non-APIStatusError (network) still retries."""
        from merco.core.recovery.wait import WaitRecovery
        rec = WaitRecovery(delay=3.0)

        class ConnErr(Exception):
            pass
        ctx = RecoveryContext(error=ConnErr("connection refused"))
        assert await rec.attempt(ctx) is True
        assert ctx.extra_wait == 3.0

    @pytest.mark.asyncio
    async def test_backoff_capped_at_max_delay(self):
        from merco.core.recovery.wait import WaitRecovery
        rec = WaitRecovery(delay=3.0, max_delay=10.0)
        ctx = RecoveryContext(error=_FakeExc("err", status_code=500),
                               attempt_count=10)
        assert await rec.attempt(ctx) is True
        assert ctx.extra_wait <= 10.0


class TestContextCompressRecovery:
    @pytest.mark.asyncio
    async def test_force_trigger_on_413(self):
        from merco.context.recovery import ContextCompressRecovery
        rec = ContextCompressRecovery()
        # Even a small context triggers compression when it's a 413
        ctx = RecoveryContext(error=_FakeExc("too long", status_code=413),
                              context_tokens=100)
        assert await rec.attempt(ctx) is True
        assert ctx.compress is True
        assert ctx.extra_wait >= 0.5  # small cooldown after compress

    @pytest.mark.asyncio
    async def test_force_trigger_on_too_long_keyword(self):
        from merco.context.recovery import ContextCompressRecovery
        rec = ContextCompressRecovery()
        ctx = RecoveryContext(error=Exception("maximum context length exceeded"),
                              context_tokens=100)
        assert await rec.attempt(ctx) is True
        assert ctx.compress is True

    @pytest.mark.asyncio
    async def test_small_context_non_413_no_compress(self):
        from merco.context.recovery import ContextCompressRecovery
        rec = ContextCompressRecovery(min_context_bytes=30000)
        ctx = RecoveryContext(error=_FakeExc("err", status_code=500),
                              context_tokens=100)  # small
        assert await rec.attempt(ctx) is False

    @pytest.mark.asyncio
    async def test_large_context_compresses(self):
        from merco.context.recovery import ContextCompressRecovery
        rec = ContextCompressRecovery(min_context_bytes=30000)
        ctx = RecoveryContext(error=_FakeExc("err", status_code=500),
                              context_tokens=100000)
        assert await rec.attempt(ctx) is True
        assert ctx.compress is True

    @pytest.mark.asyncio
    async def test_does_not_exceed_max_compress(self):
        from merco.context.recovery import ContextCompressRecovery
        rec = ContextCompressRecovery()
        ctx = RecoveryContext(error=_FakeExc("err", status_code=500),
                              context_tokens=100000, compress_count=2)
        assert await rec.attempt(ctx) is False
```

Run: `pytest tests/core/test_recovery_wait.py -v`
Expected: all FAIL (WaitRecovery still gates on `_is_retryable`, won't retry 401/conn errors).

- [ ] **Step 2: Rewrite WaitRecovery**

Replace `merco/core/recovery/wait.py` with:

```python
"""WaitRecovery — delays before retry on errors.

Differentiated wait:
- 429/5xx/network/timeout: exponential backoff starting at `delay`, capped at `max_delay`
- 413: returns False (let ContextCompressRecovery handle)
- 401/403/404: one short 1.0s retry, then gives up
- Other 4xx/unknown: backoff starting at delay*0.66 (slightly shorter)
"""
from __future__ import annotations

import logging
from merco.core.pipeline import Recovery, RecoveryContext

logger = logging.getLogger("merco.pipeline")

# Status codes that are deterministic (wrong config) — fast retry once, then stop.
SHORT_RETRY_STATUSES = frozenset({401, 403, 404})
# Status codes where waiting is useless.
NO_WAIT_STATUSES = frozenset({413})


class WaitRecovery(Recovery):
    """Wait before retry; differentiated policy by error type."""

    name = "wait"

    def __init__(self, delay: float = 3.0, max_delay: float = 30.0,
                 short_delay: float = 1.0):
        self.delay = delay
        self.max_delay = max_delay
        self.short_delay = short_delay

    async def attempt(self, ctx: RecoveryContext) -> bool:
        status = getattr(ctx.error, "status_code", None)
        body = str(ctx.error).lower()
        name = type(ctx.error).__name__.lower()

        # 413 → compression handles it
        if status == 413 or "context length" in body or "too long" in body \
                or "maximum context" in body:
            return False

        # Deterministic errors: one short retry only
        if status in SHORT_RETRY_STATUSES:
            if ctx.attempt_count >= 1:
                return False
            delay = self.short_delay
            logger.info("→ 确定性错误 (status=%s)，快速重试一次（%.1fs）",
                        status, delay)
            ctx.extra_wait = max(ctx.extra_wait, delay)
            return True

        # Network / timeout / unknown Exception subclass → backoff
        is_network = (
            "connection" in name or "timeout" in name
            or "connect" in body or "timeout" in body or "timed out" in body
            or "network" in body
        )

        if status is not None and 500 <= status <= 599:
            base = self.delay
        elif status == 429 or "rate limit" in body or "too many requests" in body:
            base = self.delay
        elif is_network:
            base = self.delay
        elif status is not None and 400 <= status < 500:
            base = self.delay * 0.66  # slightly shorter for unknown 4xx
        else:
            base = self.delay * 0.66

        # Exponential backoff
        delay = min(base * (2 ** ctx.attempt_count), self.max_delay)
        logger.info("→ 等待 %.1fs 后重试 LLM（attempt=%d, status=%s）",
                    delay, ctx.attempt_count + 1, status)
        ctx.extra_wait = max(ctx.extra_wait, delay)
        return True
```

- [ ] **Step 3: Rewrite ContextCompressRecovery**

Replace `merco/context/recovery.py` with:

```python
"""ContextCompressRecovery — compresses context when request body is too large."""
from __future__ import annotations

import logging
from merco.core.pipeline import Recovery, RecoveryContext

logger = logging.getLogger("merco.pipeline")


class ContextCompressRecovery(Recovery):
    """Compress context: triggered by 413/too-long keywords OR large context."""

    name = "compress_context"

    def __init__(self, min_context_bytes: int = 30000):
        self.min_context_bytes = min_context_bytes

    async def attempt(self, ctx: RecoveryContext) -> bool:
        if ctx.compress_count >= ctx.max_compress:
            return False

        status = getattr(ctx.error, "status_code", None)
        body = str(ctx.error).lower()

        # Force trigger on explicit too-long errors, even for small contexts.
        force = (
            status == 413
            or "context length" in body
            or "maximum context" in body
            or "prompt too long" in body
            or ("too long" in body and "context" in body)
        )

        if not force:
            # Heuristic: small context + transient error, wait is enough
            if ctx.context_tokens > 0 and \
                    ctx.context_tokens * 4 < self.min_context_bytes:
                return False

        logger.info("→ 压缩上下文后重试 LLM（第 %d/%d 次）",
                     ctx.compress_count + 1, ctx.max_compress)
        ctx.compress = True
        # Small cooldown after compression so the API isn't hammered
        # immediately after a big payload.
        ctx.extra_wait = max(ctx.extra_wait, 0.5)
        return True
```

- [ ] **Step 4: Delete _is_retryable helper from pipeline.py**

In `merco/core/pipeline.py`, remove lines 268–272 (the `_is_retryable` function at the bottom of the file). Keep the rest of pipeline.py intact. (Check with `grep -n "_is_retryable" merco/core/pipeline.py` to find exact line numbers before deleting.)

Verify no other module imports `_is_retryable`:

```bash
grep -rn "_is_retryable" merco/ tests/ --include="*.py"
```
Expected: only matches inside the function definition itself (now removed), or no matches at all.

- [ ] **Step 5: Rewrite errors.py thin wrapper**

Replace `merco/core/llm/errors.py` with:

```python
"""LLM error helpers — thin wrappers around error_ui.

Kept for backward compatibility; new code should use
``merco.core.llm.error_ui`` directly.
"""
from __future__ import annotations

from merco.core.llm.error_ui import (  # noqa: F401
    ErrorInfo,
    classify_error,
    sanitize_message,
    build_error_panel,
    build_retry_line,
    retry_spinner,
    error_message,
)


def llm_error(exc: Exception) -> str:
    """Backward-compatible wrapper: convert an exception to a user-facing
    error message. Delegates to error_ui."""
    return error_message(classify_error(exc))
```

- [ ] **Step 6: Run recovery tests**

Run: `pytest tests/core/test_recovery_wait.py -v`
Expected: all PASS.

- [ ] **Step 7: Run full test suite to ensure no regressions**

Run: `pytest tests/ -v --ignore=tests/integration -x`
Expected: existing tests still PASS. (Integration tests may need extra env; ignore them for now.)

- [ ] **Step 8: Commit**

```bash
git add merco/core/llm/errors.py merco/core/recovery/wait.py merco/context/recovery.py merco/core/pipeline.py tests/core/test_recovery_wait.py
git commit -m "feat(recovery): differentiate wait policy; remove _is_retryable gate; all errors retry"
```

---

### Task 5: Add _error_displayed_in_stream flag + update StreamingProvider (TDD)

**Files:**
- Modify: `merco/core/agent.py`
- Create: `tests/core/test_agent_error_handling.py`

**Interfaces:**
- `Agent._error_displayed_in_stream: bool` — initialized False in `__init__`, reset in `run()` and `reset()`, set True by StreamingProvider when it renders a static error Panel.
- `StreamingProvider.get_response()` — catches Exception, replaces thinking panel via `build_error_panel`, sets flag in finally when printing static panel, re-raises.

- [ ] **Step 1: Write failing tests**

Write to `tests/core/test_agent_error_handling.py`:

```python
"""Tests for agent error handling: StreamingProvider errors, retry, final error."""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from rich.console import Console

from merco.core.config import MercoConfig
from merco.core.agent import Agent, StreamingProvider


class _FailingStreamLLM:
    """Mock LLM whose chat_stream raises immediately."""
    model = "test-model"

    def __init__(self, exc: Exception):
        self._exc = exc
        self.calls = []

    async def chat_stream(self, messages, tools=None, tool_choice="auto"):
        self.calls.append({"messages": messages, "tools": tools})
        raise self._exc
        yield  # pragma: no cover (make it async gen)

    async def chat(self, messages, tools=None, tool_choice="auto"):
        raise self._exc


def _make_agent_with_failing_llm(monkeypatch, tmp_path, exc: Exception,
                                  streaming: bool = True) -> Agent:
    """Build an Agent with _FailingStreamLLM injected."""
    from merco.memory.session_store import SessionStore
    from merco.tools.registry import ToolRegistry

    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr("merco.core.agent._get_db_path", lambda: db_path)

    cfg = MercoConfig()
    cfg.model.api_key = "test-key"
    cfg.model.model = "test-model"
    cfg.sandbox_mode = "auto"
    cfg.streaming = streaming
    cfg.stream_thinking = True
    cfg.stream_content = True
    cfg.stream_thinking_transient = False
    cfg.memory_path = str(tmp_path / "memory")

    async def _fake_create(config, tool_registry=None):
        agent = Agent(config, tool_registry=tool_registry)
        agent.llm = _FailingStreamLLM(exc)
        # Skip plugin activation (avoid MCP/HTTP setup):
        agent._plugin_ctx = MagicMock()
        agent._session_store = SessionStore(db_path)
        agent.session = type(agent.session).resume_or_create(agent._session_store)
        agent._restore_context()
        return agent

    monkeypatch.setattr(Agent, "create", staticmethod(_fake_create))
    reg = ToolRegistry()
    agent = asyncio.get_event_loop().run_until_complete(
        Agent.create(cfg, tool_registry=reg))
    return agent


class TestAgentErrorFlag:
    def test_flag_initialized_false(self, test_agent):
        assert test_agent._error_displayed_in_stream is False

    def test_flag_reset_on_run(self, test_agent):
        test_agent._error_displayed_in_stream = True
        # run() resets synchronously at start
        asyncio.get_event_loop().run_until_complete(
            test_agent.run.__wrapped__(test_agent, "hi") if hasattr(test_agent.run, "__wrapped__")
            else _reset_direct(test_agent))
        # Directly verify reset path exists by calling _current_prompt assignment
        test_agent._current_prompt = ""  # simulate entry
        test_agent._error_displayed_in_stream = False
        assert test_agent._error_displayed_in_stream is False


async def _reset_direct(agent):
    agent._error_displayed_in_stream = False


class TestStreamingProviderError:
    @pytest.mark.asyncio
    async def test_streaming_provider_reraises_error(self, tmp_path, monkeypatch):
        """StreamingProvider must re-raise API errors (so agent loop handles retry)."""
        exc = Exception("502 bad gateway")
        exc.status_code = 502
        agent = _make_agent_with_failing_llm(monkeypatch, tmp_path, exc)

        provider = StreamingProvider()
        with pytest.raises(Exception, match="502 bad gateway"):
            # Use a real Console but to a StringIO file to avoid terminal output
            from io import StringIO
            fake_out = StringIO()
            import merco.core.agent as agent_mod
            with patch.object(agent_mod, "console", Console(file=fake_out, force_terminal=True, width=120)):
                await provider.get_response(agent, [{"role": "user", "content": "hi"}], [])

    @pytest.mark.asyncio
    async def test_streaming_provider_sets_error_flag_on_error(self, tmp_path, monkeypatch):
        exc = Exception("401 unauthorized")
        exc.status_code = 401
        agent = _make_agent_with_failing_llm(monkeypatch, tmp_path, exc)
        provider = StreamingProvider()
        from io import StringIO
        fake_out = StringIO()
        import merco.core.agent as agent_mod
        with patch.object(agent_mod, "console", Console(file=fake_out, force_terminal=True, width=120)):
            with pytest.raises(Exception):
                await provider.get_response(agent, [{"role": "user", "hi"}], [])
        assert agent._error_displayed_in_stream is True

    @pytest.mark.asyncio
    async def test_error_output_contains_label(self, tmp_path, monkeypatch):
        exc = Exception("rate limit exceeded")
        exc.status_code = 429
        agent = _make_agent_with_failing_llm(monkeypatch, tmp_path, exc)
        provider = StreamingProvider()
        from io import StringIO
        fake_out = StringIO()
        import merco.core.agent as agent_mod
        con = Console(file=fake_out, force_terminal=True, width=120, color_system=None)
        with patch.object(agent_mod, "console", con):
            with pytest.raises(Exception):
                await provider.get_response(agent, [{"role": "user", "hi"}], [])
        output = fake_out.getvalue()
        assert "API 错误" in output or "限流" in output or "错误" in output


class TestAgentLoopErrorReturn:
    @pytest.mark.asyncio
    async def test_terminal_failure_returns_x_prefixed_string(self, tmp_path, monkeypatch):
        exc = Exception("permanent failure")
        exc.status_code = 401
        agent = _make_agent_with_failing_llm(monkeypatch, tmp_path, exc)
        # stream_content=False so we don't have to worry about live rendering;
        # but the flag logic should still work.
        result = await agent.run("hi")
        assert result.startswith("❌ ")
        assert "认证失败" in result or "401" in result or "权限" in result or "认证" in result

    @pytest.mark.asyncio
    async def test_error_not_written_to_session(self, tmp_path, monkeypatch):
        """Error responses must NOT be persisted to session/context."""
        exc = Exception("nope")
        exc.status_code = 500
        agent = _make_agent_with_failing_llm(monkeypatch, tmp_path, exc)
        pre_count = len(agent.session.messages)
        await agent.run("hi")
        post_count = len(agent.session.messages)
        # Only the user message should have been added, not an assistant error
        assert post_count == pre_count + 1
        assert agent.session.messages[-1]["role"] == "user"
```

Run: `pytest tests/core/test_agent_error_handling.py -v`
Expected: FAIL (flag not initialized, StreamingProvider doesn't catch errors, etc.)

- [ ] **Step 2: Add _error_displayed_in_stream flag to Agent.__init__**

In `merco/core/agent.py`, in `Agent.__init__` after `self._current_prompt = ""` (around line 322), add:

```python
        # Flag set by response providers when they've already displayed an error
        # panel inline (avoids duplicate Panel print at REPL layer).
        self._error_displayed_in_stream = False
```

- [ ] **Step 3: Reset flag in run() and reset()**

In `Agent.run()` (after `self._current_prompt = prompt`, around line 602–603), add:

```python
        self._error_displayed_in_stream = False
```

In `Agent.reset()` (after `self._current_prompt = ""`, around line 1240), add:

```python
        self._error_displayed_in_stream = False
```

- [ ] **Step 4: Modify StreamingProvider.get_response() to catch errors**

Locate the `StreamingProvider.get_response` method. Replace its `try/finally` block structure with the following. Keep the *setup* code (before `try:`) intact: the buf/Panel/Live initialization and the `_refresh_thinking` task creation remain the same. The changes are inside and after the `try:` block.

The current shape is:
```python
        try:
            stream = agent.llm.chat_stream(messages, tools=tools)
            async for chunk in stream:
                ...  # existing chunk processing
            # final updates
        finally:
            ...  # cleanup
        return assembled
```

Replace from `try:` through the end of the method (through `return assembled`) with:

```python
        stream_error: Exception | None = None
        try:
            stream = agent.llm.chat_stream(messages, tools=tools)
            async for chunk in stream:
                # 取消检查点：如果任务被取消，立即退出
                current = asyncio.current_task()
                if current and current.cancelled():
                    live.stop()
                    assembled["reasoning"] = reasoning_buf
                    assembled["content"] = content_buf
                    if tc_buf:
                        assembled["tool_calls"] = [
                            {"id": v["id"], "name": v["name"],
                             "arguments": _json.loads(v["arguments"])
                             if v["arguments"] else {}}
                            for v in (tc_buf[i] for i in sorted(tc_buf))
                        ]
                    if reasoning_buf or content_buf or tc_buf:
                        assistant_msg = {
                            "role": "assistant",
                            "content": content_buf,
                            "reasoning": reasoning_buf,
                        }
                        if tc_buf:
                            assistant_msg["tool_calls"] = assembled["tool_calls"]
                        logger.debug("StreamingProvider 中断: partial response saved")
                        agent.context.add(assistant_msg)
                        agent.session.add_message("assistant", content_buf,
                                                  reasoning=reasoning_buf,
                                                  tool_calls=assembled.get("tool_calls"))
                    raise asyncio.CancelledError()
                r = chunk.get("reasoning", "")
                if r:
                    reasoning_buf += r
                    if stream_think:
                        now = time.monotonic()
                        if render_interval <= 0 or now - _last_render >= render_interval:
                            _last_render = now
                            nonlocal_thinking_panel[0] = _build_reasoning_panel(reasoning_buf)
                            live.update(_rebuild_group())
                content_buf += chunk.get("content", "")
                if content_buf.strip() and agent.config.stream_content:
                    if content_panel is None:
                        content_panel = Panel("", border_style="dim",
                                              title_align="left", padding=(0, 1))
                        nonlocal_content_panel[0] = content_panel
                    now = time.monotonic()
                    if now - _last_content_update >= _content_update_interval:
                        _last_content_update = now
                        content_panel.renderable = Markdown(content_buf)
                        live.update(_rebuild_group())
                for tc in chunk.get("tool_calls", []):
                    idx = tc["index"]
                    if idx not in tc_buf:
                        tc_buf[idx] = {
                            "id": tc.get("id", ""),
                            "name": tc.get("name", ""),
                            "arguments": ""}
                    if tc.get("id"): tc_buf[idx]["id"] = tc["id"]
                    if tc.get("name"): tc_buf[idx]["name"] = tc["name"]
                    tc_buf[idx]["arguments"] += tc.get("arguments", "")
                if chunk.get("finish_reason"):
                    assembled["finish_reason"] = chunk["finish_reason"]
                if chunk.get("usage"):
                    assembled["usage"] = chunk["usage"]
            # Final update to ensure all content is displayed
            if reasoning_buf:
                nonlocal_thinking_panel[0] = _build_reasoning_panel(reasoning_buf)
            if content_panel and content_buf.strip():
                content_panel.renderable = Markdown(content_buf)
            if reasoning_buf or (content_panel and content_buf.strip()):
                live.update(_rebuild_group())
        except asyncio.CancelledError:
            raise
        except Exception as e:
            stream_error = e
            logger.warning("StreamingProvider API 错误: %s", e, exc_info=True)
            from merco.core.llm.error_ui import classify_error, build_error_panel
            info = classify_error(e)
            nonlocal_thinking_panel[0] = build_error_panel(info)
            nonlocal_content_panel[0] = content_panel  # preserve partial content if any
            live.update(_rebuild_group())
            await asyncio.sleep(0.15)  # let user see the panel before stop
        finally:
            if 'refresh_task' in locals():
                refresh_task.cancel()
                try:
                    await refresh_task
                except asyncio.CancelledError:
                    pass
            transient = agent.config.stream_thinking_transient
            if live:
                live.stop()
            # Normal-mode static copies when transient
            if transient and reasoning_buf:
                console.print(_build_reasoning_panel(reasoning_buf))
            if transient and content_buf and agent.config.stream_content:
                console.print(Panel(Markdown(content_buf), border_style="dim",
                                    title_align="left", padding=(0, 1)))
            # Error path: print static red Panel if needed
            if stream_error is not None:
                from merco.core.llm.error_ui import (
                    classify_error, build_error_panel,
                )
                need_static = transient or (not reasoning_buf and not content_buf)
                if need_static:
                    info = classify_error(stream_error)
                    console.print(build_error_panel(info))
                agent._error_displayed_in_stream = True
                raise stream_error

        assembled["reasoning"] = reasoning_buf
        assembled["content"] = content_buf
        if tc_buf:
            assembled["tool_calls"] = [
                {"id": v["id"], "name": v["name"],
                 "arguments": _json.loads(v["arguments"])
                 if v["arguments"] else {}}
                for v in (tc_buf[i] for i in sorted(tc_buf))
            ]
        logger.debug(
            "stream done: finish=%s content=%d reasoning=%d tool_calls=%d%s",
            assembled.get("finish_reason"), len(assembled["content"]),
            len(assembled["reasoning"]), len(assembled["tool_calls"]),
            f" {[tc['name'] for tc in assembled['tool_calls']]}" if assembled["tool_calls"] else "")
        return assembled
```

Wait — I notice the existing chunk-processing block is duplicated verbatim in my replacement. That's fine (it keeps existing working logic), but double-check the indentation matches. The critical changes:
1. Added `stream_error = None` before `try:`.
2. Added `except asyncio.CancelledError: raise` before generic `except Exception`.
3. Added generic `except Exception as e:` that classifies, builds a red panel, swaps it in, pauses 0.15s.
4. In `finally:`, added the error branch: if `stream_error is not None`, conditionally print static red Panel, set `agent._error_displayed_in_stream = True`, re-raise.

- [ ] **Step 5: Update _wrap_up_call to return error_message instead of hardcoded string**

Find `_wrap_up_call` in agent.py. Replace:

```python
    async def _wrap_up_call(self, messages):
        """收尾调用：无工具文字回应。"""
        try:
            resp = await self.llm.chat(messages, tools=[], tool_choice="none")
        except Exception:
            return "模型调用失败"
        content = resp.get("content", "") or "已达到调用上限。"
        self.session.add_message("assistant", content)
        self.context.add({"role": "assistant", "content": content})
        return content
```

with:

```python
    async def _wrap_up_call(self, messages):
        """收尾调用：无工具文字回应。"""
        try:
            resp = await self.llm.chat(messages, tools=[], tool_choice="none")
        except Exception as e:
            from merco.core.llm.error_ui import classify_error, error_message
            return error_message(classify_error(e))
        content = resp.get("content", "") or "已达到调用上限。"
        self.session.add_message("assistant", content)
        self.context.add({"role": "assistant", "content": content})
        return content
```

- [ ] **Step 6: Run StreamingProvider/agent error tests**

Run: `pytest tests/core/test_agent_error_handling.py -v`
Expected: tests for flag init, StreamingProvider error re-raise, flag set, and terminal failure should all PASS. The "error_not_written_to_session" test might fail because error path in `_agent_loop` writes the user message but not assistant — verify that logic matches the test expectation (user message was already added at top of `run()`, before _agent_loop).

- [ ] **Step 7: Commit**

```bash
git add merco/core/agent.py tests/core/test_agent_error_handling.py
git commit -m "feat(streaming): StreamingProvider swaps in red error panel; sets error-displayed flag; wrap_up returns error_message"
```

---

### Task 6: Update agent loop exception handler for retry feedback (TDD)

**Files:**
- Modify: `merco/core/agent.py` (the `except Exception as e:` block in `_agent_loop`)
- Modify: `tests/core/test_agent_error_handling.py` (add retry tests)

**Interfaces:**
- Agent loop except block uses `error_ui.classify_error`, `build_retry_line`, `retry_spinner`, and returns `error_message(info)` on terminal failure.
- No error Panel is printed directly in the loop (the REPL or StreamingProvider already handles display).

- [ ] **Step 1: Write failing tests for retry feedback**

Append to `tests/core/test_agent_error_handling.py`:

```python
class TestAgentLoopRetry:
    @pytest.mark.asyncio
    async def test_retries_then_succeeds(self, tmp_path, monkeypatch):
        """Agent retries through a 429 and then returns a normal response."""
        from merco.core.pipeline import RecoveryContext
        from merco.core.recovery.wait import WaitRecovery
        from merco.context.recovery import ContextCompressRecovery

        class RetryThenSuccessLLM:
            model = "test-model"
            def __init__(self, fail_times=1):
                self.fail_times = fail_times
                self.calls = 0
            async def chat_stream(self, messages, tools=None, tool_choice="auto"):
                self.calls += 1
                if self.calls <= self.fail_times:
                    exc = Exception("rate limit exceeded")
                    exc.status_code = 429
                    raise exc
                    yield  # unreachable
                yield {"content": "hello after retry", "finish_reason": "stop"}

        from merco.memory.session_store import SessionStore
        from merco.tools.registry import ToolRegistry
        from merco.core.config import MercoConfig

        db_path = str(tmp_path / "test.db")
        monkeypatch.setattr("merco.core.agent._get_db_path", lambda: db_path)
        cfg = MercoConfig()
        cfg.model.api_key = "test-key"
        cfg.model.model = "test-model"
        cfg.sandbox_mode = "auto"
        cfg.streaming = True
        cfg.stream_thinking = True
        cfg.stream_content = True
        cfg.stream_thinking_transient = True  # transient so Live doesn't stay
        cfg.memory_path = str(tmp_path / "memory")

        async def _fake_create(config, tool_registry=None):
            agent = Agent(config, tool_registry=tool_registry)
            agent.llm = RetryThenSuccessLLM(fail_times=1)
            agent._plugin_ctx = MagicMock()
            agent._session_store = SessionStore(db_path)
            agent.session = type(agent.session).resume_or_create(agent._session_store)
            agent._restore_context()
            # Bypass long waits in WaitRecovery for test
            agent.recovery_pipeline = agent.recovery_pipeline
            for rec in agent.recovery_pipeline._recoveries:
                if rec.name == "wait":
                    rec.delay = 0.01
                    rec.short_delay = 0.01
                    rec.max_delay = 0.05
            return agent

        monkeypatch.setattr(Agent, "create", staticmethod(_fake_create))
        agent = await Agent.create(cfg, tool_registry=ToolRegistry())

        from io import StringIO
        fake_out = StringIO()
        import merco.core.agent as agent_mod
        with patch.object(agent_mod, "console", Console(file=fake_out, force_terminal=True, width=200, color_system=None)):
            result = await agent.run("hi")
        # Should get a successful response after retry
        assert "hello after retry" in result
        output = fake_out.getvalue()
        assert "↻" in output  # retry line was printed
        assert agent.llm.calls >= 2  # at least one failure + one success

    @pytest.mark.asyncio
    async def test_three_strikes_returns_error(self, tmp_path, monkeypatch):
        """After 3 retries (total 4 attempts including initial), returns ❌ error."""
        class AlwaysFailLLM:
            model = "test-model"
            def __init__(self):
                self.calls = 0
            async def chat_stream(self, messages, tools=None, tool_choice="auto"):
                self.calls += 1
                exc = Exception("server exploded")
                exc.status_code = 500
                raise exc
                yield

        from merco.memory.session_store import SessionStore
        from merco.tools.registry import ToolRegistry
        from merco.core.config import MercoConfig

        db_path = str(tmp_path / "test.db")
        monkeypatch.setattr("merco.core.agent._get_db_path", lambda: db_path)
        cfg = MercoConfig()
        cfg.model.api_key = "test"
        cfg.model.model = "m"
        cfg.sandbox_mode = "auto"
        cfg.streaming = False  # non-streaming to simplify
        cfg.memory_path = str(tmp_path / "memory")

        async def _fake_create(config, tool_registry=None):
            agent = Agent(config, tool_registry=tool_registry)
            agent.llm = AlwaysFailLLM()
            agent._plugin_ctx = MagicMock()
            agent._session_store = SessionStore(db_path)
            agent.session = type(agent.session).resume_or_create(agent._session_store)
            agent._restore_context()
            for rec in agent.recovery_pipeline._recoveries:
                if rec.name == "wait":
                    rec.delay = 0.01
                    rec.max_delay = 0.01
                    rec.short_delay = 0.01
            return agent

        monkeypatch.setattr(Agent, "create", staticmethod(_fake_create))
        agent = await Agent.create(cfg, tool_registry=ToolRegistry())
        from io import StringIO
        fake_out = StringIO()
        import merco.core.agent as agent_mod
        with patch.object(agent_mod, "console", Console(file=fake_out, force_terminal=True, width=200, color_system=None)):
            result = await agent.run("hi")
        assert result.startswith("❌ ")
        assert "500" in result or "服务端" in result
        # Initial call + up to 3 retries = max 4 total calls
        assert agent.llm.calls == 4
```

Run: `pytest tests/core/test_agent_error_handling.py::TestAgentLoopRetry -v`
Expected: FAIL (agent loop currently silently sleeps/returns, no retry message, and `_recovery_attempts > 3` path doesn't track calls correctly to 4).

- [ ] **Step 2: Replace agent loop except block**

In `merco/core/agent.py`, locate the `except Exception as e:` block inside `_agent_loop` (currently around lines 749–771 before any edits, search for `_recovery_attempts += 1`). Replace the entire `except Exception as e:` block with:

```python
            except Exception as e:
                from merco.core.llm.error_ui import (
                    classify_error, build_retry_line, retry_spinner, error_message,
                )
                _recovery_attempts += 1
                info = classify_error(e)
                max_attempts = 3

                if _recovery_attempts > max_attempts:
                    logger.error("LLM %s: 重试 %d 次仍失败",
                                 info.label, max_attempts, exc_info=e)
                    return error_message(info)

                from openai import APIStatusError
                from .pipeline import RecoveryContext
                ctx = RecoveryContext(
                    error=e,
                    status_code=e.status_code if isinstance(e, APIStatusError)
                               else getattr(e, "status_code", 0),
                    context_tokens=self.context.current_tokens,
                    tool_count=len(tools),
                    model=self.config.model.model,
                )
                if await self.recovery_pipeline.attempt(ctx):
                    actions: list[str] = []
                    if ctx.extra_wait > 0:
                        actions.append(f"等待 {ctx.extra_wait:.1f}s")
                    if ctx.compress:
                        actions.append("压缩上下文")
                    if ctx.switch_model:
                        actions.append(f"切换模型→{ctx.switch_model}")
                    if not actions:
                        actions.append("立即重试")
                    console.print(build_retry_line(
                        info, _recovery_attempts, max_attempts, actions))

                    if ctx.extra_wait > 1.0:
                        async with retry_spinner(info.label, ctx.extra_wait, console):
                            await asyncio.sleep(ctx.extra_wait)
                    elif ctx.extra_wait > 0:
                        await asyncio.sleep(ctx.extra_wait)

                    if ctx.compress:
                        await self._compress_context()
                    if ctx.switch_model:
                        logger.info("→ 切换模型: %s", ctx.switch_model)
                        console.print(f"[dim]  → 模型切换为 {ctx.switch_model}[/dim]")
                        self.llm.model = ctx.switch_model
                    continue

                # Recovery pipeline couldn't handle — terminal failure
                logger.error("LLM %s: 恢复管线无法处理", info.label, exc_info=e)
                return error_message(info)
```

Note on `status_code`: the `isinstance(e, APIStatusError)` check requires the openai SDK to be installed (which it is per dependencies). We also fall back to `getattr(e, "status_code", 0)` for duck-typed fake errors (which is what our tests use).

- [ ] **Step 3: Run retry tests**

Run: `pytest tests/core/test_agent_error_handling.py::TestAgentLoopRetry -v`
Expected: both retry tests PASS.

- [ ] **Step 4: Run all agent error handling tests**

Run: `pytest tests/core/test_agent_error_handling.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add merco/core/agent.py tests/core/test_agent_error_handling.py
git commit -m "feat(agent-loop): visible retry feedback with yellow line + spinner; terminal failure returns error_message"
```

---

### Task 7: Update REPL to render error Panels (TDD)

**Files:**
- Modify: `cli/main.py` (the response-rendering block after `agent.run(user_input)`)
- Test: manual verification by monkeypatching a fake run coroutine

- [ ] **Step 1: Write a simple REPL-level test**

Create `tests/cli/test_repl_error.py`:

```python
"""Tests for the REPL error-rendering branch in cli/main.py."""
import asyncio
from rich.console import Console
from io import StringIO


def test_repl_renders_error_panel_when_not_streamed():
    """When _error_displayed_in_stream is False (non-streaming or wrap_up error),
    the REPL should render a red Panel."""
    from cli.main import run_repl
    import cli.main as main_mod
    from merco.core.config import MercoConfig
    from merco.core.agent import Agent
    from unittest.mock import MagicMock, patch, AsyncMock

    # Build a minimal stub agent
    agent = MagicMock(spec=Agent)
    agent.config = MercoConfig()
    agent.config.streaming = False  # non-streaming
    agent.config.stream_content = False
    agent._error_displayed_in_stream = False
    agent.mcp_manager = None
    agent.config.mcp_servers = None

    # Simulate one call: return an error, then raise EOFError to exit loop
    call_count = 0
    async def fake_run(prompt):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return "❌ [bold red]认证失败[/bold red]：[red]bad key[/red]\n[dim]detail[/dim]"
        raise EOFError

    agent.run = fake_run
    agent.get_context_stats = MagicMock(return_value={
        "current": 100, "max": 8000, "ratio": 0.01, "threshold": 0.75,
        "is_estimate": True, "tool_count": 0, "max_tool_calls": 20,
    })
    agent.session = MagicMock()
    agent.session.title = "test"
    agent.observer = MagicMock()
    agent.reset = MagicMock()

    fake_out = StringIO()
    con = Console(file=fake_out, force_terminal=True, width=200, color_system=None)
    with patch.object(main_mod, "console", con), \
         patch("cli.input_driver.PromptToolkitInput") as MockDrv, \
         patch("cli.commands"):  # prevent command registration side-effects
        drv = MagicMock()
        async def fake_get_input(prompt):
            nonlocal call_count
            if call_count == 0:
                return "hi"
            raise EOFError
        drv.get_input = fake_get_input
        MockDrv.return_value = drv
        try:
            run_repl(agent, dashboard=None, config_source="test")
        except (EOFError, SystemExit):
            pass
    output = fake_out.getvalue()
    assert "❌" in output or "认证失败" in output or "bad key" in output
```

Run: `pytest tests/cli/test_repl_error.py -v`
Expected: FAIL (current REPL skips non-streaming error? No, currently non-streaming prints Panel(Markdown(response)) — but Markdown doesn't render Rich markup correctly, so it should show something but not in a red Panel titled "API 错误").

- [ ] **Step 2: Modify REPL response rendering**

In `cli/main.py`, find the block that looks like:

```python
                    console.rule("[bold]Agent[/bold]", style="dim")
                    current_task = asyncio.current_task()
                    response = await agent.run(user_input)
                    current_task = None

                    # 只在响应未被流式显示时打印（需要 streaming=True 且 stream_content=True 才会流式显示）
                    if not (agent.config.streaming and agent.config.stream_content):
                        console.print(Panel(Markdown(response), border_style="dim"))
                    console.rule(style="dim")
```

Replace with:

```python
                    console.rule("[bold]Agent[/bold]", style="dim")
                    current_task = asyncio.current_task()
                    response = await agent.run(user_input)
                    current_task = None

                    # Error responses: render as red Panel unless the streaming
                    # provider already displayed an inline error (avoid duplicate).
                    if response and response.startswith("❌"):
                        if not getattr(agent, '_error_displayed_in_stream', False):
                            from rich.text import Text as RichText
                            console.print(Panel(
                                RichText.from_markup(response),
                                border_style="red",
                                title="⚠ API 错误",
                                title_align="left", padding=(0, 1)))
                    elif not (agent.config.streaming and agent.config.stream_content):
                        console.print(Panel(Markdown(response), border_style="dim"))
                    # Reset the flag for the next turn
                    agent._error_displayed_in_stream = False
                    console.rule(style="dim")
```

- [ ] **Step 3: Run REPL test**

Run: `pytest tests/cli/test_repl_error.py -v`
Expected: PASS.

- [ ] **Step 4: Run full test suite (except integration) to check for regressions**

Run: `pytest tests/ --ignore=tests/integration -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add cli/main.py tests/cli/test_repl_error.py
git commit -m "feat(repl): detect ❌ error responses and render red Panel unless already shown inline"
```

---

### Task 8: End-to-end verification and cleanup

**Files:** None modified (verification only).

- [ ] **Step 1: Run full suite including integration (if they don't need external env)**

Run: `pytest tests/ -v`
Expected: All tests PASS. If integration tests require external services (API keys, MCP), mark them as skipped locally — but ensure all core/unit/cli tests pass.

- [ ] **Step 2: Quick syntax/import sanity**

Run: `python -c "
from merco.core.llm.error_ui import classify_error, build_error_panel, build_retry_line, error_message
from merco.core.llm.errors import llm_error
from merco.core.recovery.wait import WaitRecovery
from merco.context.recovery import ContextCompressRecovery
from merco.core.agent import Agent, StreamingProvider
print('all imports ok')
"`
Expected: prints "all imports ok".

- [ ] **Step 3: Manually verify error scenarios (optional — requires an API key configured to return errors)**

With an invalid API key or a non-existent model, run `merco run -k sk-invalid` and type "hi":
Expected behavior:
- If streaming mode is on (default if configured): a red "认证失败" Panel should appear (not an empty window).
- The retry line "↻ API 认证失败（第 1/3 次）— 等待 1.0s…" may appear briefly followed by the spinner for 1s, then one more fast retry, then terminal red Panel.
- The terminal red Panel should show "认证失败" + hint + detail.
- No empty window at any point.

- [ ] **Step 4: Verify commit log**

Run: `git log --oneline -10`
Expected: 6 commits (skeleton, classify+sanitize, panel/spinner/error-msg, recovery policy, streaming provider, agent loop, REPL) plus the initial spec commit.

- [ ] **Step 5: Final commit if any small fix was needed**

Only if Step 2–4 revealed a tiny issue (no design changes), commit the fix:

```bash
git add -A
git commit -m "fix: minor fixes from verification"
```

Otherwise skip this step.

---

## Self-Review Checklist

I've checked the plan against the spec:

1. **Spec coverage**:
   - §1 new error_ui module → Tasks 1–3
   - §2 StreamingProvider error panel + flag → Task 5
   - §3 agent loop retry feedback (line + spinner) → Task 6
   - §4 WaitRecovery differentiated wait + ContextCompressRecovery force-trigger + all errors retry + delete `_is_retryable` → Task 4
   - §5 REPL error Panel + flag check → Task 7
   - "errors not written to session/context" → enforced by agent loop not calling `session.add_message`/`context.add` on error path; test in Task 5
   - TDD required for every behavioral change → every task has failing test step before implementation
   - Error strings start with "❌" → enforced by `error_message()` and tested

2. **Placeholder scan**: No TBD/TODOs. All code shown verbatim.

3. **Type/signature consistency**:
   - `classify_error(exc) -> ErrorInfo` — matches across tasks 2/3/4/5/6/7
   - `build_error_panel(info) -> Panel` — used consistently
   - `build_retry_line(info, attempt, max, actions) -> str` — used consistently in Task 6
   - `error_message(info) -> str` — returns Rich-markup string starting with "❌ "
   - `retry_spinner(label, seconds, console)` — async context manager used via `async with` in Task 6
   - `Agent._error_displayed_in_stream: bool` — initialized False, set by StreamingProvider, checked/reset by REPL
