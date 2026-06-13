---
name: sandbox-tool-guard-integration
description: 打通 Sandbox ToolGuard 到 ToolRegistry，实现工具执行前的安全守卫
created: 2026-06-13
status: in_progress
---

# 实现计划：打通 Sandbox → ToolRegistry

## 目标

在 `ToolRegistry.execute()` 统一调用 ToolGuard，所有工具（bash/file/edit）执行前先过守卫。

## 架构

```
LLM → tool_calls → Registry.execute("bash", command="rm -rf /")
                                    ↓
                            ToolGuard.check("bash", args)
                                    ↓
                    SecurityChecker (正则兜底，硬拦截)
                                    ↓
                        ToolGuard 规则链匹配
                                    ↓
                    ask → 弹窗确认 → 放行/拦截
                    deny → 直接拦截
                    allow → 直接放行
                                    ↓
                            工具真正执行
```

## 任务清单

### 任务 1：修改 `merco/tools/registry.py`

**文件**: `merco/tools/registry.py`

**变更**:
1. 导入 `ToolGuard` 从 `merco.sandbox`
2. 创建模块级 `tool_guard` 单例
3. 在 `execute()` 开头调 `await tool_guard.check(tool_name, kwargs)`
4. 检查返回 `False` 则拦截，返回结构化错误

**实现细节**:

```python
# merco/tools/registry.py

from merco.sandbox import tool_guard  # 新增导入

async def execute(self, tool_name: str, **kwargs) -> dict:
    """执行指定工具（异常自动转为结构化错误，喂回 LLM 自愈）"""
    tool = self.get(tool_name)
    if tool is None:
        return {"error": f"工具 '{tool_name}' 不存在"}

    # 新增：安全守卫检查
    if not await tool_guard.check(tool_name, kwargs):
        return {
            "error": "操作被安全守卫拦截",
            "tool": tool_name,
            "args": kwargs,
        }

    try:
        return await tool.execute(**kwargs)
    except Exception as e:
        from merco.core.self_healing import tool_error
        return tool_error(e, tool_name, getattr(tool, 'parameters', None))
```

### 任务 2：更新 `merco/sandbox/__init__.py`

**文件**: `merco/sandbox/__init__.py`

**变更**:
1. 导入 `ToolGuard`, `GuardRule`
2. 添加 `tool_guard` 单例（从配置加载 sandbox_rules）
3. 添加 `create_tool_guard()` 工厂函数
4. 导出 `ToolGuard`, `GuardRule`, `tool_guard`

**实现细节**:

```python
# merco/sandbox/__init__.py

from .guard import ToolGuard, GuardRule, _DEFAULT_RULES

# 工厂函数：从配置加载守卫
def create_tool_guard(config=None) -> ToolGuard:
    """从 MercoConfig 加载 sandbox_rules 创建 ToolGuard"""
    if config is None:
        from merco.core.config import MercoConfig
        config = MercoConfig.load()

    mode = getattr(config, 'sandbox_mode', 'ask')
    user_rules = getattr(config, 'sandbox_rules', []) or []
    return ToolGuard(mode=mode, user_rules=user_rules)

# 模块级单例（默认配置）
try:
    tool_guard = create_tool_guard()
except Exception:
    # 配置未初始化时用默认值
    tool_guard = ToolGuard(mode='ask', user_rules=[])

__all__ = ['ToolGuard', 'GuardRule', 'tool_guard', 'create_tool_guard']
```

### 任务 3：测试验证

**测试文件**: `tests/test_sandbox_guard.py`

**测试用例**:
1. `test_guard_blocks_dangerous_command` — `rm -rf /` 被拦截
2. `test_guard_prompts_sensitive_command` — `pip install` 弹窗确认
3. `test_guard_allows_safe_command` — `ls` 直接放行
4. `test_guard_blocks_path_traversal` — `../../../etc/passwd` 被拦截
5. `test_registry_calls_guard` — Registry.execute 调用守卫
6. `test_registry_blocks_when_guard_denies` — 守卫拒绝时 Registry 返回错误

## 配置项

`merco.json` 中可配置：

```json
{
  "sandbox_mode": "ask",    // "ask" | "auto" | "deny"
  "sandbox_rules": [
    {"tool": "bash", "pattern": "DROP TABLE", "action": "deny"},
    {"tool": "bash", "pattern": "curl | bash", "action": "deny"}
  ]
}
```

- `sandbox_mode: "auto"` — 跳过所有确认，直接放行（CI 环境）
- `sandbox_mode: "deny"` — 所有命令都拦截（最严格）

## 验收标准

1. ✅ `rm -rf /` 被 SecurityChecker 正则兜底拦截
2. ✅ `pip install` 匹配规则 `pip `，action=ask，弹窗确认
3. ✅ `ls` 无匹配规则，直接放行
4. ✅ 文件路径 `../../../etc/passwd` 被拦截
5. ✅ `sandbox_mode: "auto"` 跳过所有确认
6. ✅ 守卫拒绝时 Registry 返回结构化错误

## 依赖

- `merco/sandbox/guard.py` — 已实现，保持不变
- `merco/sandbox/security.py` — 已实现，保持不变
- `merco/core/config.py` — 已支持 sandbox_mode/sandbox_rules

## 不在此计划范围

- 单独的 sandbox 隔离执行（容器化沙箱）
- 工具执行超时控制
- 审计日志持久化