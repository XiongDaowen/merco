# merco self_healing 拆分 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 self_healing.py 拆成三个文件：core/self_healing 保留可扩展 hook、tools/errors.py 装工具错误、core/llm/errors.py 装 LLM 错误

**Architecture:** 按调用方分组；core 不再依赖 openai；行为完全不变

**Tech Stack:** Python 3.12, pytest

---

## 文件结构

| 文件 | 职责 |
|------|------|
| `merco/tools/errors.py` | tool_error, classify_error, empty_response, ERROR_CATEGORIES, 内部辅助 |
| `merco/core/llm/errors.py` | llm_error, _is_retryable_llm_error |
| `merco/core/self_healing.py` | 仅保留 register_handler / _extra_handlers / _apply_custom_handlers |
| `merco/tools/middleware.py` | import 更新到 tools.errors |
| `merco/core/empty_response.py` | import 更新到 tools.errors |
| `merco/core/pipeline.py` | import 更新到 core.llm.errors |
| `merco/core/agent.py` | llm_error import 更新到 core.llm.errors |

---

## Task 1: 移出 tools/errors.py

**Files:**
- Create: `merco/tools/errors.py`
- Modify: `tests/tools/test_middleware.py`

- [ ] **Step 1: Append import test**

Append to `tests/tools/test_middleware.py` a new import smoke test at the end:

```python
def test_tools_errors_module_imports():
    from merco.tools.errors import tool_error, classify_error, empty_response
    assert tool_error.__name__ == "tool_error"
    assert classify_error.__name__ == "classify_error"
    assert empty_response.__name__ == "empty_response"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/xiowen/code/merco && python3 -m pytest tests/tools/test_middleware.py -v -k "tools_errors_module"`
Expected: ImportError (merco.tools.errors does not exist)

- [ ] **Step 3: Create tools/errors.py**

Create `merco/tools/errors.py` with the following contents (copied verbatim from `merco/core/self_healing.py` lines 18-105 and 141-152 and 172-194):

```python
"""工具执行错误处理 — 把异常转为 LLM 可消费的结构化 dict。

边界：错误分类 + 公共消息脱敏。LLM 错误（APIStatusError 等）由 core.llm.errors 处理。
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("merco.tools.errors")


ERROR_CATEGORIES = {
    "param_mismatch": "参数不匹配",
    "tool_not_found": "工具不存在",
    "timeout": "执行超时",
    "permission": "权限不足",
    "network": "网络错误",
    "resource_not_found": "资源不存在",
    "internal": "内部错误",
    "unknown": "未知错误",
}


def classify_error(exc: Exception) -> str:
    """将异常映射到错误类别"""
    if isinstance(exc, TypeError):
        return "param_mismatch"
    if isinstance(exc, TimeoutError):
        return "timeout"
    if isinstance(exc, PermissionError):
        return "permission"
    if isinstance(exc, FileNotFoundError):
        return "resource_not_found"
    if isinstance(exc, ConnectionError):
        return "network"
    if isinstance(exc, OSError):
        return "network"
    if isinstance(exc, ValueError):
        return "param_mismatch"
    return "unknown"


def tool_error(
    exc: Exception,
    tool_name: str,
    tool_schema: dict | None = None,
) -> dict:
    """将工具执行异常转为 LLM 可读的结构化错误"""
    category = classify_error(exc)
    label = ERROR_CATEGORIES.get(category, "未知错误")
    result: dict[str, Any] = {
        "error": f"[{label}] {tool_name}: {_public_message(exc)}",
        "category": category,
        "tool": tool_name,
    }
    if category == "param_mismatch":
        hint = _params_hint(tool_schema)
        result["suggestion"] = f"参数类型或值不正确。{hint}"
        if tool_schema:
            result["available_params"] = _param_names(tool_schema)
    elif category == "tool_not_found":
        result["suggestion"] = "该工具不可用。请使用其他可用工具完成用户请求。"
    elif category == "timeout":
        result["suggestion"] = "操作超时。可尝试减少数据量、拆分请求，或使用其他工具。"
    elif category == "permission":
        result["suggestion"] = "权限不足。请检查文件权限，或使用其他路径/工具。"
    elif category == "network":
        result["suggestion"] = "网络请求失败。可重试，或检查 URL 是否正确。"
    elif category == "resource_not_found":
        result["suggestion"] = "资源（文件/路径）不存在。请检查路径拼写，或搜索确认位置。"
    else:
        result["suggestion"] = "执行时发生意外错误。请尝试其他方式完成用户请求。"
        logger.warning("工具 %s 未知异常", tool_name, exc_info=True)
    return result


def empty_response() -> dict:
    """空回复错误 — 回调 LLM 让它产出实际内容"""
    return {
        "error": "[空回复] 你既没有回复用户也没有调用工具。"
                 "请直接回答用户，或使用工具推进任务。",
        "category": "empty_response",
        "suggestion": "请直接回复用户，或调用工具获取信息。",
    }


def _public_message(exc: Exception) -> str:
    msg = str(exc)
    if len(msg) > 300:
        msg = msg[:300] + "..."
    return msg


def _params_hint(schema: dict | None) -> str:
    if not schema:
        return "请检查工具调用参数。"
    names = _param_names(schema)
    required = schema.get("required", [])
    if required:
        return f"必需: {', '.join(required)}。可用: {', '.join(names)}。"
    return f"可用参数: {', '.join(names)}。"


def _param_names(schema: dict) -> list[str]:
    props = schema.get("properties", {})
    return list(props.keys()) if isinstance(props, dict) else []
```

- [ ] **Step 4: Run tests**

Run: `cd /home/xiowen/code/merco && python3 -m pytest tests/tools/test_middleware.py -v`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
cd /home/xiowen/code/merco
git add merco/tools/errors.py tests/tools/test_middleware.py
git commit -m "feat: add merco.tools.errors with tool_error classify empty_response"
```

---

## Task 2: 移出 core/llm/errors.py

**Files:**
- Create: `merco/core/llm/__init__.py`
- Create: `merco/core/llm/errors.py`
- Modify: `tests/core/test_self_healing.py`

- [ ] **Step 1: Append import test**

Append to `tests/core/test_self_healing.py`:

```python
def test_llm_errors_module_imports():
    from merco.core.llm.errors import llm_error, _is_retryable_llm_error
    assert llm_error.__name__ == "llm_error"
    assert _is_retryable_llm_error.__name__ == "_is_retryable_llm_error"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/xiowen/code/merco && python3 -m pytest tests/core/test_self_healing.py -v -k "llm_errors_module"`
Expected: ImportError

- [ ] **Step 3: Create core/llm/errors.py**

Create `merco/core/llm/__init__.py`:

```python
"""LLM 子系统：模型调用和错误处理。"""
```

Create `merco/core/llm/errors.py`:

```python
"""LLM 调用错误处理 — 把 API 异常分类并脱敏。

边界：HTTP 状态码、关键字匹配脱敏、Retry 判定。不感知具体 provider 协议。
"""
from __future__ import annotations


def _is_retryable_llm_error(exc: Exception) -> bool:
    """判断 LLM API 错误是否可重试。"""
    try:
        from openai import APIStatusError
    except ImportError:
        return False
    if not isinstance(exc, APIStatusError):
        return False

    status = exc.status_code
    if status == 413:
        return True
    if status == 429:
        return True
    if 500 <= status <= 599:
        return True
    body = str(exc).lower()
    return any(kw in body for kw in (
        "rate limit", "too many requests", "overloaded",
        "capacity", "throttl", "temporarily unavailable",
        "context length", "too long", "maximum context",
        "reduce the length", "prompt too long",
    ))


def llm_error(exc: Exception) -> str:
    """将 LLM 调用异常转为对用户友好的错误消息。"""
    msg = str(exc)
    for keyword in ("api_key", "token", "secret", "key", "authorization"):
        if keyword.lower() in msg.lower():
            msg = "(包含敏感信息，已脱敏)"
            break
    return f"模型调用失败，请检查 API key 和网络连接。（{msg}）"
```

- [ ] **Step 4: Run tests**

Run: `cd /home/xiowen/code/merco && python3 -m pytest tests/core/test_self_healing.py -v`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
cd /home/xiowen/code/merco
git add merco/core/llm/ tests/core/test_self_healing.py
git commit -m "feat: add merco.core.llm.errors with llm_error and retryable check"
```

---

## Task 3: 缩减 core/self_healing.py

**Files:**
- Modify: `merco/core/self_healing.py`
- Test: `tests/core/test_self_healing.py`

- [ ] **Step 1: Append clean test**

Append to `tests/core/test_self_healing.py`:

```python
def test_core_self_healing_does_not_import_openai():
    """core 不应再 import openai（拆分到 llm/errors.py）"""
    import inspect
    from merco.core import self_healing
    src = inspect.getsource(self_healing)
    assert "openai" not in src.lower()
    assert "tool_error" not in src
    assert "classify_error" not in src
    assert "empty_response" not in src
    assert "llm_error" not in src
    assert "_is_retryable_llm_error" not in src
```

- [ ] **Step 2: Rewrite core/self_healing.py**

Replace entire file contents with:

```python
"""可扩展错误处理 — 注册自定义异常 handler。

边界：仅作为异常 handler 注册表。工具错误（tool_error）走 merco.tools.errors，LLM 错误（llm_error）走 merco.core.llm.errors。
"""
from __future__ import annotations

import logging
from typing import Callable

logger = logging.getLogger("merco.self_healing")


_extra_handlers: dict[type, Callable] = {}


def register_handler(exc_type: type, handler: Callable) -> None:
    """注册自定义异常处理器。

    handler 签名: (exc, tool_name, tool_schema) -> dict | None
    返回 None 表示不处理，走默认逻辑。
    """
    _extra_handlers[exc_type] = handler


def _apply_custom_handlers(
    exc: Exception, tool_name: str, tool_schema: dict | None,
) -> dict | None:
    """依次尝试注册的自定义 handler"""
    for exc_type, handler in _extra_handlers.items():
        if isinstance(exc, exc_type):
            try:
                return handler(exc, tool_name, tool_schema)
            except Exception:
                logger.warning("自定义 handler 异常", exc_info=True)
    return None
```

- [ ] **Step 3: Run tests**

Run: `cd /home/xiowen/code/merco && python3 -m pytest tests/core/test_self_healing.py -v`
Expected: all pass

- [ ] **Step 4: Commit**

```bash
cd /home/xiowen/code/merco
git add merco/core/self_healing.py tests/core/test_self_healing.py
git commit -m "refactor: trim core/self_healing to handler registry only"
```

---

## Task 4: 更新 import 路径

**Files:**
- Modify: `merco/tools/middleware.py`
- Modify: `merco/core/empty_response.py`
- Modify: `merco/core/pipeline.py`
- Modify: `merco/core/agent.py`

- [ ] **Step 1: Update tools/middleware.py import**

In `merco/tools/middleware.py` line 118:

```python
        from merco.tools.errors import tool_error
```

- [ ] **Step 2: Update core/empty_response.py import**

In `merco/core/empty_response.py` line 21:

```python
        from merco.tools.errors import empty_response
```

- [ ] **Step 3: Update core/pipeline.py import**

In `merco/core/pipeline.py` line 270 (the `_is_retryable` function):

```python
    from merco.core.llm.errors import _is_retryable_llm_error
```

- [ ] **Step 4: Update core/agent.py imports**

In `merco/core/agent.py` lines 667 and 685 (the two `from .self_healing import llm_error` lines):

```python
                    from merco.core.llm.errors import llm_error
```

- [ ] **Step 5: Run full suite**

```bash
cd /home/xiowen/code/merco
python3 -m pytest tests/tools/test_middleware.py tests/core/test_self_healing.py tests/integration/test_scenarios.py -v 2>&1 | tail -25
```

- [ ] **Step 6: Commit**

```bash
cd /home/xiowen/code/merco
git add merco/tools/middleware.py merco/core/empty_response.py merco/core/pipeline.py merco/core/agent.py
git commit -m "refactor: update imports for split self_healing"
```

---

## Task 5: 文档更新

**Files:**
- Modify: `docs/project-vision/references/architecture-refactor-plan.md`
- Modify: `docs/project-vision/references/progress.md`

- [ ] **Step 1: Mark Phase 2.5 done**

In `architecture-refactor-plan.md`:

```markdown
### 2.5 self_healing 拆分 ✅ 已完成
```

- [ ] **Step 2: Add progress entry**

In `progress.md` add:

```markdown
- **self_healing 拆分（架构重构 Phase 2.5）**:
  - `core/self_healing.py` 仅保留 `register_handler` 可扩展 hook
  - 工具错误迁至 `merco/tools/errors.py`（tool_error/classify_error/empty_response）
  - LLM 错误迁至 `merco/core/llm/errors.py`（llm_error/_is_retryable_llm_error）
  - core 不再 import openai
```

- [ ] **Step 3: Commit**

```bash
cd /home/xiowen/code/merco
git add docs/project-vision/references/architecture-refactor-plan.md docs/project-vision/references/progress.md
git commit -m "docs: mark self_healing split complete"
```

---

## Self-Review

**Spec coverage:**
- ✅ tools/errors.py (Task 1)
- ✅ core/llm/errors.py (Task 2)
- ✅ core/self_healing.py 缩减 (Task 3)
- ✅ import 路径更新 (Task 4)
- ✅ 文档 (Task 5)

**Behavior safety:** 函数体逐字迁移，调用方 import 更新，行为完全不变。
