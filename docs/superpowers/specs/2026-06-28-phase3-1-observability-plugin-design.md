# Phase 3.1：ObservabilityPlugin + Agent Async Factory 设计规格

> 日期: 2026-06-28
> 基于: `docs/project-vision/references/architecture-refactor-plan.md`
> 前置: Phase 3.7 HookRegistry 升级已完成

## 背景

Phase 3 的目标是把 `Agent.__init__` 中硬初始化的模块迁移为插件。3.1 迁移 observability：当前 `Agent.__init__` 直接执行 `self.observer = Observer(self.hooks)`。

这不是单纯“把一行构造挪到插件里”，因为 `Observer` 有初始化时序要求：`Agent._restore_context()` 会读取 session metadata 并调用 `self.observer.restore(...)`。因此 observer 必须在 `_restore_context()` 前存在。

同时，现有插件激活逻辑在 running event loop 中走 `asyncio.ensure_future(self.plugin_manager.activate_all())`，这是 fire-and-forget，不保证插件在 Agent 后续代码访问前完成。若直接把 observer 放进普通插件激活流程，会产生竞态。

## 目标

1. 新增 `ObservabilityPlugin`，由插件创建 `Observer(ctx.hooks)`。
2. 引入 `Agent.create(...)` async factory，提供确定性插件激活路径。
3. 保持现有 `Agent(...)` 构造方式暂时可用，作为 legacy path，避免一次性迁移所有调用点。
4. 确保新 factory 路径中 `_restore_context()` 发生在 `ObservabilityPlugin` 激活之后。
5. 保持 `agent.observer` 对外兼容。
6. 明确后续 3.2-3.6 应逐步把调用点迁移到 `Agent.create(...)`。

## 非目标

- 不在 3.1 中迁移 SkillRegistry / MCP / SubAgent / Web / Scheduler。
- 不强制本轮把所有 `Agent(...)` 调用点改成 `await Agent.create(...)`。
- 不重写完整 PluginManager 生命周期系统。
- 不改变 Observer 内部计数逻辑或 hook 订阅事件。

---

## 设计

### 1. ObservabilityPlugin

新增文件：`merco/plugins/builtin/observability/plugin.py`

```python
class ObservabilityPlugin(Plugin):
    name = "observability"
    version = "1.0.0"
    description = "Creates the observability observer"

    async def activate(self, ctx):
        from merco.observability.observer import Observer
        ctx.observer = Observer(ctx.hooks)
```

Observer 的 hook 订阅仍由 `Observer.__init__` 完成。插件只负责创建并挂到 `ctx.observer`。

### 2. PluginContext observer 可选

`PluginContext.__init__` 中：

```python
observer: Observer | None = None
```

原因：在插件激活前，ctx 需要先存在，但 observer 尚未创建。

### 3. Agent.create async factory

新增权威初始化路径：

```python
@classmethod
async def create(cls, config: MercoConfig, tool_registry=None, skill_registry=None) -> "Agent":
    agent = cls(
        config=config,
        tool_registry=tool_registry,
        skill_registry=skill_registry,
        _defer_plugin_init=True,
    )
    await agent._initialize_async_plugins()
    return agent
```

`Agent.__init__` 新增内部参数：

```python
def __init__(..., _defer_plugin_init: bool = False):
```

- 默认 `False`：legacy path，保持当前 `Agent(...)` 可用。
- `Agent.create()` 传 `True`：factory path，不走 fire-and-forget，不提前 `_restore_context()`。

### 4. 初始化顺序（factory path）

```text
Agent.create()
  1. agent = Agent(..., _defer_plugin_init=True)
  2. Agent.__init__ 初始化同步基础设施：hooks、guard、tool middleware、session store、pipelines、prompt_builder、memory、context_pipeline、profiles、todo/subagent、loop_policies
  3. Agent.__init__ 创建 PluginContext(observer=None)
  4. Agent.__init__ 注册 ObservabilityPlugin + SuperpowerPlugin，但不 activate_all，不 _restore_context()
  5. create() await agent.plugin_manager.activate("observability")
  6. create() 同步 agent.observer = agent._plugin_ctx.observer
  7. create() assert agent.observer is not None
  8. create() 执行 agent._restore_context()
  9. create() await agent.plugin_manager.activate_all() 激活普通 enabled 插件
  10. return agent
```

关键：factory path 中 `_restore_context()` 必须移出 `__init__` 的早期位置，放在 observability 激活之后。

### 5. legacy Agent(...) 行为

短期内保留：

```python
agent = Agent(config, tool_registry)
```

legacy path 的目的只是避免一次性破坏现有 CLI、测试和 SubAgentManager 调用点。它可以继续直接保证 `agent.observer` 可用。

这是一个**明确的过渡例外**：

- 新代码和新测试应优先使用 `await Agent.create(...)`。
- legacy `Agent(...)` 保持兼容，但不代表最终架构。
- 后续 3.2-3.6 逐步迁移调用点后，再删除 legacy observer 直构路径。

### 6. agent.observer 兼容

无论 legacy path 还是 factory path，外部都能：

```python
agent.observer.snapshot()
agent.observer.restore(data)
agent.observer.report()
```

factory path 中，ObservabilityPlugin 激活后同步：

```python
agent.observer = agent._plugin_ctx.observer
```

这样保持现有代码对 `self.observer` 的访问方式不变，避免本轮引入 property 重写和更大范围改动。

### 7. 重复激活处理

factory path 会先显式激活 `observability`，随后再调用 `activate_all()` 激活普通 enabled 插件。因此需要避免重复激活 observability。

推荐改法：`PluginManager.activate(name)` 若插件已在 `_active` 中，直接返回：

```python
async def activate(self, name: str) -> None:
    if name in self._active:
        return
    ...
```

这样不需要给 `activate_all()` 增加特殊排除逻辑，也有利于所有插件生命周期幂等。

---

## 测试策略

### Plugin 单元测试

- `ObservabilityPlugin.activate(ctx)` 后 `ctx.observer` 是 `Observer`
- Observer 订阅了 `llm.chat`, `tool.after_execute`, `conversation.turn`, `agent.start` 等事件
- metadata: name/version/description 稳定
- `PluginContext(..., observer omitted)` 合法，且初始 `ctx.observer is None`

### PluginManager 幂等测试

- 同一个 plugin 连续 `activate(name)` 两次，只执行一次 `plugin.activate(ctx)`
- `_active` 中已有插件时，`activate_all()` 不会重复激活

### Agent factory 集成测试

- `agent = await Agent.create(...)` 后 `agent.observer` 是 `Observer`
- factory path 中 `_restore_context()` 能恢复 observer snapshot
- factory path 中 `observability` 在 `plugin_manager.active_plugins`
- factory path 中 `SuperpowerPlugin` 仍可通过 `activate_all()` 激活
- legacy `Agent(...)` 仍通过现有测试

### 回归测试

- `tests/plugins/`
- `tests/observability/test_observer.py`
- `tests/core/test_agent.py`
- `tests/integration/test_agent_loop.py`

---

## 风险与约束

1. **双路径复杂度**
   - 短期同时存在 legacy `Agent(...)` 和 async `Agent.create(...)`。
   - 这是为了避免一次性大迁移。

2. **legacy 仍有 Observer 直构**
   - 这是过渡例外，不是最终架构。
   - 新路径必须通过 ObservabilityPlugin 创建 observer。

3. **重复激活风险**
   - 用 `PluginManager.activate()` 幂等化解决。

4. **restore 顺序风险**
   - factory path 必须保证 `_restore_context()` 在 observer 创建后执行。

5. **后续迁移依赖**
   - 3.2+ 应逐步让更多调用点使用 `Agent.create()`，最终移除 legacy 初始化。

## 用户确认的设计选择

用户选择方案 B：**Agent async factory**。

执行策略：**渐进兼容**：建立 factory，但本轮不强制所有 Agent 创建点迁移。legacy path 明确保留为过渡兼容层。

## 自审结论

已修正以下问题：

- `Agent.create()` 示例现在明确传 `_defer_plugin_init=True`。
- 明确 legacy path 是过渡例外，不是最终插件化架构。
- 明确 factory path 不在 `__init__` 中 `_restore_context()`，而是在 observability 激活后 restore。
- 增加 PluginManager 激活幂等要求，避免 `observability` 被 `activate_all()` 重复激活。

本 spec 聚焦 3.1，可进入 implementation plan；后续 3.2-3.6 再逐步扩大 `Agent.create()` 的使用范围。
