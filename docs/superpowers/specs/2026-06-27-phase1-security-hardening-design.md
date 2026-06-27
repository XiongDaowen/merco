# merco Phase 1 安全加固设计

> 最后更新: 2026-06-27
> 基于: `docs/project-vision/references/architecture-refactor-plan.md`

## 目标

完成架构审查报告中的 Phase 1 安全加固：收紧 PluginContext 暴露面、修复插件激活时序、删除重复/废弃代码。

## 范围

### 1. PluginContext 安全加固

#### 问题

`PluginContext` 当前直接暴露 `security_pipeline`，插件可直接修改安全策略链。这属于高风险扩展点：插件如果能随意插入 allow-all policy，就可以绕过沙箱。

同时 `add_processor(name, proc)` 通过字符串访问任意属性，等于允许插件写入任意 pipeline-like 对象。

#### 方案

- 从 `PluginContext.__init__` 移除 `security_pipeline`
- 删除 `self.security_pipeline`
- `add_processor()` 增加白名单：

```python
_PIPELINE_WHITELIST = {
    "result_pipeline",
    "recovery_pipeline",
    "memory_save_pipeline",
    "context_pipeline",
}


def add_processor(self, pipeline_name: str, processor) -> None:
    if pipeline_name not in _PIPELINE_WHITELIST:
        raise ValueError(f"Pipeline '{pipeline_name}' not extensible")
    pipeline = getattr(self, pipeline_name, None)
    if pipeline and hasattr(pipeline, 'use'):
        pipeline.use(processor)
```

### 2. Plugin activate_all 时序修复

#### 问题

Agent 构造中先创建 `PluginContext` 并激活插件，之后才把部分扩展点赋值到 `self._plugin_ctx`：

- `context_pipeline`
- `todo_manager`
- `sub_agent_manager`
- `memory_backends`
- `agent_profiles`

这会导致插件 `activate(ctx)` 时拿不到这些扩展点。

#### 方案

重排 `Agent.__init__` 组装顺序：

```text
1. 创建所有原子/可扩展子系统
   - hooks / observer
   - tool_registry
   - pipelines
   - prompt_builder
   - memory_backends / memory_store / recaller / memory_save_pipeline
   - context_pipeline
   - todo_manager / sub_agent_manager
   - agent_profiles

2. 创建 PluginContext，一次性传入全部扩展点

3. 创建 PluginManager，注册内置插件

4. activate_all()
```

**原则：PluginContext 在插件激活前必须完整。**

### 3. 删除重复/废弃代码

#### 删除文件

| 文件 | 原因 | 替代 |
|------|------|------|
| `merco/memory/compressor.py` | 与 `context/processors/compress.py` 重复 | `CompressProcessor` |
| `merco/sandbox/permissions.py` | 与 `guard.py` / PermissionPolicy 重叠 | `PermissionPolicy` |
| `merco/sandbox/isolation.py` | 未使用 | 后续如果需要重建为 SandboxIsolationPlugin |

#### 删除条件

删除前必须 grep 确认代码无引用：

```bash
grep -R "memory.compressor\|ContextCompressor" merco tests
grep -R "sandbox.permissions\|PermissionManager" merco tests
grep -R "sandbox.isolation\|SandboxIsolation" merco tests
```

如果仍有引用，先迁移再删除。

## 非目标

- 不重构 AgentFactory
- 不做 LoopPolicy
- 不做 ToolRegistry 中间件
- 不升级 HookRegistry
- 不改 PermissionPolicy 行为

## 测试计划

| 测试 | 目的 |
|------|------|
| `tests/plugins/` | PluginContext 变更不破坏插件系统 |
| `tests/sandbox/` | PermissionPolicy/ToolGuard 行为不变 |
| `tests/context/` | 删除 compressor.py 后 ContextPipeline 仍正常 |
| `tests/memory/` | MemoryBackend/MemoryStore 行为不变 |
| `tests/integration/test_scenarios.py -k guard` | Agent + guard 集成不变 |

## 成功标准

1. PluginContext 不再暴露 `security_pipeline`
2. `add_processor("security_pipeline", ...)` 抛 ValueError
3. 插件 activate 时可访问 context_pipeline/todo_manager/sub_agent_manager/memory_backends/agent_profiles
4. 废弃文件删除后无 import error
5. 相关测试全部通过
