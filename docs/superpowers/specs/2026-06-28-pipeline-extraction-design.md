# merco Pipeline 处理器外移设计

> 最后更新: 2026-06-28
> Phase 2.4: Pipeline 内置处理器外移

## 目标

让 `merco/core/pipeline.py` 只保留 Pipeline 框架和 ABC，不再承载具体业务处理器。具体处理器迁移到各自子系统，符合"原子能力内聚，拓展能力外移"原则。

## 现状

`merco/core/pipeline.py` 当前混合了：

### 框架层（应该保留）
- `ProcessContext`
- `Processor`
- `ResultPipeline`
- `RecoveryContext`
- `Recovery`
- `RecoveryPipeline`
- `EmptyResponseContext`
- `EmptyResponseStrategy`
- `EmptyResponsePipeline`

### 具体实现（应该外移）
- `TruncationProcessor`
- `SkillViewProcessor`
- `WaitRecovery`
- `ContextCompressRecovery`
- `ToolReduceRecovery`
- `ModelFallbackRecovery`
- `CallbackEmptyResponse`

## 目标结构

| 当前类 | 目标文件 | 归属 |
|---|---|---|
| `TruncationProcessor` | `merco/tools/processors/truncation.py` | tools |
| `SkillViewProcessor` | `merco/skills/processors.py` | skills |
| `WaitRecovery` | `merco/core/recovery/wait.py` | core recovery |
| `ContextCompressRecovery` | `merco/context/recovery.py` | context |
| `ToolReduceRecovery` | `merco/tools/recovery.py` | tools |
| `ModelFallbackRecovery` | `merco/core/recovery/model_fallback.py` | llm/core |
| `CallbackEmptyResponse` | `merco/core/empty_response.py` | core |

## Agent import 更新

当前：

```python
from .pipeline import (
    ResultPipeline, RecoveryPipeline, EmptyResponsePipeline,
    TruncationProcessor, SkillViewProcessor,
    WaitRecovery, ContextCompressRecovery, CallbackEmptyResponse
)
```

改为：

```python
from .pipeline import ResultPipeline, RecoveryPipeline, EmptyResponsePipeline
from merco.tools.processors.truncation import TruncationProcessor
from merco.skills.processors import SkillViewProcessor
from merco.core.recovery.wait import WaitRecovery
from merco.context.recovery import ContextCompressRecovery
from merco.core.empty_response import CallbackEmptyResponse
```

## 向后兼容策略

本轮 **不保留 re-export**。理由：

1. 这些类当前只有 Agent 内部使用
2. 目标是让 `pipeline.py` 真正干净
3. 若测试暴露外部 import，再按需补兼容层

## 文件结构

```
merco/core/
├── pipeline.py              # 只保留 ABC + Pipeline 框架
├── empty_response.py        # CallbackEmptyResponse
└── recovery/
    ├── __init__.py
    ├── wait.py              # WaitRecovery
    └── model_fallback.py    # ModelFallbackRecovery

merco/context/
└── recovery.py              # ContextCompressRecovery

merco/tools/
├── processors/
│   ├── __init__.py
│   └── truncation.py        # TruncationProcessor
└── recovery.py              # ToolReduceRecovery

merco/skills/
└── processors.py            # SkillViewProcessor
```

## 测试计划

| 测试 | 目的 |
|------|------|
| existing pipeline tests | 框架仍可用 |
| agent integration tests | Agent import 更新正确 |
| skill view tests | SkillViewProcessor 仍工作 |
| recovery tests | WaitRecovery/ContextCompressRecovery 仍工作 |

## 成功标准

1. `merco/core/pipeline.py` 不再包含具体处理器类
2. Agent 启动和测试正常
3. 所有迁移类行为不变
4. `grep -n "class TruncationProcessor\|class WaitRecovery" merco/core/pipeline.py` 无结果

## 非目标

- 不重构 Pipeline 框架本身
- 不修改处理器行为
- 不新增功能
- 不修改 RecoveryPipeline 执行逻辑
