# merco Pipeline 处理器外移 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 `merco/core/pipeline.py` 只保留 Pipeline 框架和 ABC，具体处理器迁移到各自子系统

**Architecture:** 纯移动代码，不改行为；Agent imports 更新到新模块；不保留 re-export

**Tech Stack:** Python 3.12, pytest

---

## 文件结构

| 文件 | 职责 |
|------|------|
| `merco/core/pipeline.py` | 只保留 ProcessContext/Processor/ResultPipeline/RecoveryContext/Recovery/RecoveryPipeline/EmptyResponseContext/EmptyResponseStrategy/EmptyResponsePipeline |
| `merco/tools/processors/truncation.py` | TruncationProcessor |
| `merco/skills/processors.py` | SkillViewProcessor |
| `merco/core/recovery/wait.py` | WaitRecovery |
| `merco/context/recovery.py` | ContextCompressRecovery |
| `merco/tools/recovery.py` | ToolReduceRecovery |
| `merco/core/recovery/model_fallback.py` | ModelFallbackRecovery |
| `merco/core/empty_response.py` | CallbackEmptyResponse |
| `merco/core/agent.py` | import 更新 |
| `tests/core/test_pipeline_extraction.py` | import + pipeline clean 验证 |

---

## Task 1: 移出 ResultPipeline processors

**Files:**
- Create: `merco/tools/processors/__init__.py`
- Create: `merco/tools/processors/truncation.py`
- Create/Modify: `merco/skills/processors.py`
- Modify: `merco/core/pipeline.py`
- Test: `tests/core/test_pipeline_extraction.py`

- [ ] **Step 1: Write smoke tests**

Create `tests/core/test_pipeline_extraction.py`:

```python
"""Pipeline 处理器外移回归测试"""


def test_result_processors_import_from_new_locations():
    from merco.tools.processors.truncation import TruncationProcessor
    from merco.skills.processors import SkillViewProcessor

    assert TruncationProcessor.__name__ == "TruncationProcessor"
    assert SkillViewProcessor.__name__ == "SkillViewProcessor"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/xiowen/code/merco && python3 -m pytest tests/core/test_pipeline_extraction.py -v`
Expected: ImportError (new modules do not exist)

- [ ] **Step 3: Move classes**

Move exact class bodies from `merco/core/pipeline.py`:

- `TruncationProcessor` → `merco/tools/processors/truncation.py`
- `SkillViewProcessor` → `merco/skills/processors.py`

Create `merco/tools/processors/__init__.py`:

```python
"""Tool result processors."""
from .truncation import TruncationProcessor

__all__ = ["TruncationProcessor"]
```

Create `merco/tools/processors/truncation.py` with imports copied from `pipeline.py` as needed:

```python
"""TruncationProcessor — truncates large tool results."""
from __future__ import annotations

import time
import logging
from merco.core.pipeline import Processor, ProcessContext

logger = logging.getLogger("merco.pipeline")

# Paste TruncationProcessor class here unchanged
```

Create `merco/skills/processors.py`:

```python
"""Skill-related result processors."""
from __future__ import annotations

import logging
from merco.core.pipeline import Processor, ProcessContext

logger = logging.getLogger("merco.pipeline")

# Paste SkillViewProcessor class here unchanged
```

Remove both class definitions from `merco/core/pipeline.py`.

- [ ] **Step 4: Run tests**

Run: `cd /home/xiowen/code/merco && python3 -m pytest tests/core/test_pipeline_extraction.py tests/integration/test_scenarios.py -v -k "simple_conversation or tool_call_chain or result_processors" 2>&1 | tail -20`

- [ ] **Step 5: Commit**

```bash
cd /home/xiowen/code/merco
git add merco/core/pipeline.py merco/tools/processors/ merco/skills/processors.py tests/core/test_pipeline_extraction.py
git commit -m "refactor: move result processors out of core pipeline"
```

---

## Task 2: 移出 Recovery processors

**Files:**
- Create: `merco/core/recovery/__init__.py`
- Create: `merco/core/recovery/wait.py`
- Create: `merco/core/recovery/model_fallback.py`
- Create: `merco/context/recovery.py`
- Create: `merco/tools/recovery.py`
- Modify: `merco/core/pipeline.py`
- Modify: `tests/core/test_pipeline_extraction.py`

- [ ] **Step 1: Append import tests**

Append to `tests/core/test_pipeline_extraction.py`:

```python

def test_recoveries_import_from_new_locations():
    from merco.core.recovery.wait import WaitRecovery
    from merco.context.recovery import ContextCompressRecovery
    from merco.tools.recovery import ToolReduceRecovery
    from merco.core.recovery.model_fallback import ModelFallbackRecovery

    assert WaitRecovery.__name__ == "WaitRecovery"
    assert ContextCompressRecovery.__name__ == "ContextCompressRecovery"
    assert ToolReduceRecovery.__name__ == "ToolReduceRecovery"
    assert ModelFallbackRecovery.__name__ == "ModelFallbackRecovery"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/xiowen/code/merco && python3 -m pytest tests/core/test_pipeline_extraction.py -v -k recoveries`
Expected: ImportError

- [ ] **Step 3: Move classes**

Move exact class bodies from `merco/core/pipeline.py`:

- `WaitRecovery` → `merco/core/recovery/wait.py`
- `ModelFallbackRecovery` → `merco/core/recovery/model_fallback.py`
- `ContextCompressRecovery` → `merco/context/recovery.py`
- `ToolReduceRecovery` → `merco/tools/recovery.py`

Create `merco/core/recovery/__init__.py`:

```python
"""Recovery strategies."""
from .wait import WaitRecovery
from .model_fallback import ModelFallbackRecovery

__all__ = ["WaitRecovery", "ModelFallbackRecovery"]
```

Each moved module should import its framework base/context from `merco.core.pipeline`, for example:

```python
from merco.core.pipeline import Recovery, RecoveryContext, _is_retryable
```

If `_is_retryable` is private but required, keep `_is_retryable` in `pipeline.py` for now (framework helper) and import it. Do not change behavior.

Remove moved class definitions from `merco/core/pipeline.py`.

- [ ] **Step 4: Run recovery tests**

Run: `cd /home/xiowen/code/merco && python3 -m pytest tests/core/test_self_healing.py tests/integration/test_scenarios.py::test_recovery_pipeline_retries_on_5xx tests/core/test_pipeline_extraction.py -v 2>&1 | tail -25`

- [ ] **Step 5: Commit**

```bash
cd /home/xiowen/code/merco
git add merco/core/pipeline.py merco/core/recovery/ merco/context/recovery.py merco/tools/recovery.py tests/core/test_pipeline_extraction.py
git commit -m "refactor: move recovery strategies out of core pipeline"
```

---

## Task 3: 移出 EmptyResponse strategy

**Files:**
- Create: `merco/core/empty_response.py`
- Modify: `merco/core/pipeline.py`
- Modify: `tests/core/test_pipeline_extraction.py`

- [ ] **Step 1: Append import test**

Append to `tests/core/test_pipeline_extraction.py`:

```python

def test_empty_response_strategy_import_from_new_location():
    from merco.core.empty_response import CallbackEmptyResponse
    assert CallbackEmptyResponse.__name__ == "CallbackEmptyResponse"
```

- [ ] **Step 2: Move CallbackEmptyResponse**

Move `CallbackEmptyResponse` class from `merco/core/pipeline.py` to `merco/core/empty_response.py`:

```python
"""Empty response strategies."""
from __future__ import annotations

import logging
from merco.core.pipeline import EmptyResponseStrategy, EmptyResponseContext

logger = logging.getLogger("merco.pipeline")

# Paste CallbackEmptyResponse class here unchanged
```

Remove `CallbackEmptyResponse` from `pipeline.py`.

- [ ] **Step 3: Run tests**

Run: `cd /home/xiowen/code/merco && python3 -m pytest tests/core/test_pipeline_extraction.py tests/integration/test_scenarios.py -v -k "empty_response or simple_conversation" 2>&1 | tail -20`

- [ ] **Step 4: Commit**

```bash
cd /home/xiowen/code/merco
git add merco/core/pipeline.py merco/core/empty_response.py tests/core/test_pipeline_extraction.py
git commit -m "refactor: move empty response strategy out of core pipeline"
```

---

## Task 4: 更新 Agent imports + 全量清理

**Files:**
- Modify: `merco/core/agent.py`
- Test: `tests/core/test_pipeline_extraction.py`

- [ ] **Step 1: Update imports in agent.py**

Find current import block in `Agent.__init__`:

```python
from .pipeline import (ResultPipeline, TruncationProcessor,
                       SkillViewProcessor, RecoveryPipeline,
                       WaitRecovery, ContextCompressRecovery,
                       EmptyResponsePipeline, CallbackEmptyResponse)
```

Replace with:

```python
from .pipeline import ResultPipeline, RecoveryPipeline, EmptyResponsePipeline
from merco.tools.processors.truncation import TruncationProcessor
from merco.skills.processors import SkillViewProcessor
from merco.core.recovery.wait import WaitRecovery
from merco.context.recovery import ContextCompressRecovery
from merco.core.empty_response import CallbackEmptyResponse
```

- [ ] **Step 2: Add pipeline clean test**

Append to `tests/core/test_pipeline_extraction.py`:

```python

def test_core_pipeline_no_concrete_processors():
    import inspect
    import merco.core.pipeline as p
    src = inspect.getsource(p)
    forbidden = [
        "class TruncationProcessor",
        "class SkillViewProcessor",
        "class WaitRecovery",
        "class ContextCompressRecovery",
        "class ToolReduceRecovery",
        "class ModelFallbackRecovery",
        "class CallbackEmptyResponse",
    ]
    for item in forbidden:
        assert item not in src
```

- [ ] **Step 3: Run syntax + integration tests**

Run:

```bash
cd /home/xiowen/code/merco
python3 -m py_compile merco/core/agent.py merco/core/pipeline.py merco/tools/processors/truncation.py merco/skills/processors.py merco/core/recovery/wait.py merco/context/recovery.py merco/tools/recovery.py merco/core/recovery/model_fallback.py merco/core/empty_response.py
python3 -m pytest tests/core/test_pipeline_extraction.py tests/integration/test_scenarios.py::test_simple_conversation tests/integration/test_scenarios.py::test_tool_call_chain tests/integration/test_scenarios.py::test_recovery_pipeline_retries_on_5xx -v
```

- [ ] **Step 4: Commit**

```bash
cd /home/xiowen/code/merco
git add merco/core/agent.py tests/core/test_pipeline_extraction.py
git commit -m "refactor: update Agent imports for extracted pipeline processors"
```

---

## Task 5: 文档更新

**Files:**
- Modify: `docs/project-vision/references/architecture-refactor-plan.md`
- Modify: `docs/project-vision/references/progress.md`

- [ ] **Step 1: Mark Phase 2.4 done**

In `architecture-refactor-plan.md` mark:

```markdown
### 2.4 Pipeline 内置处理器外移 ✅ 已完成
```

- [ ] **Step 2: Add progress entry**

In `progress.md` add:

```markdown
- **Pipeline 处理器外移（架构重构 Phase 2.4）**:
  - `core/pipeline.py` 只保留 Pipeline 框架/ABC/Context
  - TruncationProcessor → `tools/processors/truncation.py`
  - SkillViewProcessor → `skills/processors.py`
  - WaitRecovery/ModelFallbackRecovery → `core/recovery/`
  - ContextCompressRecovery → `context/recovery.py`
  - ToolReduceRecovery → `tools/recovery.py`
  - CallbackEmptyResponse → `core/empty_response.py`
```

- [ ] **Step 3: Commit**

```bash
cd /home/xiowen/code/merco
git add docs/project-vision/references/architecture-refactor-plan.md docs/project-vision/references/progress.md
git commit -m "docs: mark pipeline processor extraction complete"
```

---

## Self-Review

**Spec coverage:**
- ✅ all concrete processors moved
- ✅ pipeline.py clean test
- ✅ Agent imports updated
- ✅ behavior unchanged
- ✅ docs updated

**Risk note:** No re-export by design per spec. If any tests or code import concrete processors from `merco.core.pipeline`, update those imports to new locations.
