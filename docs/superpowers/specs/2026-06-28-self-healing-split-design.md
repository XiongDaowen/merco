# merco self_healing 拆分设计

> 最后更新: 2026-06-28
> Phase 2.5: self_healing 拆分

## 目标

`self_healing.py` 混了工具错误和 LLM 错误两个领域，且 `_is_retryable_llm_error` 依赖 openai，让 core 反向依赖外部库。拆分让 core 不再 import openai，tools 错误归 tools 子系统。

## 现状

`merco/core/self_healing.py` 包含：

| 分类 | 函数 | 依赖 |
|------|------|------|
| 工具错误 | `tool_error`, `classify_error`, `empty_response` | 无外部依赖 |
| LLM 错误 | `llm_error`, `_is_retryable_llm_error` | `openai.APIStatusError` |
| 可扩展 | `_extra_handlers`, `register_handler`, `_apply_custom_handlers` | 无外部依赖 |

## 拆分方案

| 文件 | 内容 |
|------|------|
| `merco/core/self_healing.py` | 只保留可扩展 hook：`_extra_handlers`, `register_handler`, `_apply_custom_handlers` |
| `merco/tools/errors.py` | `tool_error`, `classify_error`, `empty_response`, `ERROR_CATEGORIES`, `_public_message`, `_params_hint`, `_param_names` |
| `merco/core/llm/errors.py` | `llm_error`, `_is_retryable_llm_error` |

## 内部 import 更新

| 文件 | 旧 import | 新 import |
|------|----------|----------|
| `merco/tools/middleware.py` | `from merco.core.self_healing import tool_error` | `from merco.tools.errors import tool_error` |
| `merco/core/empty_response.py` | `from merco.core.self_healing import empty_response` | `from merco.tools.errors import empty_response` |
| `merco/core/pipeline.py` (`_is_retryable`) | `from merco.core.self_healing import _is_retryable_llm_error` | `from merco.core.llm.errors import _is_retryable_llm_error` |

## 向后兼容

- `self_healing.py` 不再 re-export，调用方更新 import 路径
- 行为完全不变
- 测试需要更新 import（但逻辑不变）

## 文件结构

```
merco/core/
├── self_healing.py      # 只保留可扩展 hook
├── llm/
│   ├── __init__.py
│   └── errors.py        # llm_error + _is_retryable_llm_error
└── empty_response.py    # 已有 CallbackEmptyStrategy

merco/tools/
├── middleware.py        # 已有，import 更新
└── errors.py            # tool_error + classify_error + empty_response
```

## 测试计划

| 测试 | 目的 |
|------|------|
| `tests/core/test_self_healing.py` | register_handler 仍工作 |
| `tests/tools/test_middleware.py` | ErrorHandlingMiddleware 仍工作 |
| `tests/core/test_self_healing.py` 测试 retryable 改 import | 仍正确分类 |
| `tests/integration/test_scenarios.py` | 集成仍工作 |

## 成功标准

1. `self_healing.py` 不再 import openai
2. `core/pipeline.py` 不再 import openai（通过 llm/errors 间接）
3. 所有现有测试通过
4. register_handler 行为不变

## 非目标

- 不修改错误分类逻辑
- 不修改 llm_error 文案
- 不修改 _is_retryable_llm_error 启发式
- 不重构 _apply_custom_handlers
