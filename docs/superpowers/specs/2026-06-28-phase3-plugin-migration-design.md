# Phase 3：模块插件化迁移 — 设计规格

> 日期: 2026-06-28
> 基于: `docs/project-vision/references/architecture-refactor-plan.md`

## 概述

Phase 3 将 Agent.__init__ 中硬初始化的子系统迁移到独立插件中，并升级 HookRegistry 支持拦截型 Hook。

**核心理念：** 新增能力 = 新增 Plugin 类并注册，不改 Agent 核心代码。

本轮先实现 **3.7 HookRegistry 升级**，再逐步迁移 3.1-3.6 的模块插件。

## 整体架构

```
Agent.__init__ (精简后)
├── 核心原子能力
│   ├── HookRegistry → PluginContext.hooks
│   ├── ToolRegistry → PluginContext.tool_registry
│   ├── LLMClient, Session, Context, Config
│   ├── Pipeline 框架, Guard, Middleware
│   └── PluginManager + PluginContext
│
└── 可拔插能力
    ├── ObservabilityPlugin → ctx.observer
    ├── SkillPlugin → ctx.skill_registry
    ├── MCPPlugin → ctx.mcp_manager
    ├── SubAgentPlugin → ctx.todo_manager + ctx.sub_agent_manager
    ├── WebPlugin → 工具注册
    ├── SchedulerPlugin → ctx.scheduler
    └── 自定义插件
```

---

## 3.7 HookRegistry 升级（先做）

### 动机

当前 HookRegistry 是 fire-and-forget：handler 被调用后返回值被忽略。插件只能「观察」，不能「影响」。升级后 handler 可通过返回 HookResult 修改后续 handler 看到的数据，并让调用方选择是否消费这些修改。

### HookResult 语义

```python
from dataclasses import dataclass

@dataclass
class HookResult:
    """Hook handler 的结构化返回值。

    - 返回 None：完全向后兼容，等同现有 fire-and-forget。
    - data：合并进当前事件 kwargs；后续 handler 会看到更新后的 kwargs。
    - stop：停止后续 handler 链；调用方可根据 stop 决定是否短路业务流程。
    """
    data: dict | None = None
    stop: bool = False
```

**重要约定：**
- `stop=True` 只表示「停止 hook handler 链」。是否跳过业务流程由 emit() 的调用方决定。
- `data` 永远是「事件 kwargs 的更新」，不是业务对象本身。
  - 对 `llm.after_chat(response=response)`，handler 要返回 `HookResult(data={"response": new_response})`。
  - 不是返回 `HookResult(data={"content": "..."})`。

### emit() 行为

`emit()` 对所有 hook 统一支持 HookResult，但旧 handler 无需修改。

```python
async def emit(self, event: str, **kwargs) -> HookResult | None:
    changed = False
    current = dict(kwargs)

    for handler in self._hooks.get(event, []):
        try:
            res = handler(**current)
            if inspect.isawaitable(res):
                res = await res
        except Exception:
            logger.debug("hook %s handler error", event, exc_info=True)
            continue

        if isinstance(res, HookResult):
            if res.data:
                current.update(res.data)
                changed = True
            if res.stop:
                return HookResult(data=current, stop=True)

    if changed:
        return HookResult(data=current, stop=False)
    return None
```

关键特性:
- **向后兼容** — 现有 handler 返回 None，行为不变
- **data-only 不丢失** — 只要任一 handler 返回 data，emit() 最终返回合并后的 kwargs
- **handler 异常隔离** — 单个 handler 失败不影响其他 handler
- **异步健壮性** — 用 `inspect.isawaitable()` 兼容 async function、返回 coroutine 的 callable object 等场景
- **全面升级** — 所有 hook 都能返回 HookResult；但只有调用方读取返回值时才会影响业务流程

### 新增 Hook 入口

在 Agent._agent_loop() 中新增两个调用方会消费返回值的 hook：

1. **`llm.before_chat`** — LLM 调用前触发
   - 入参: `messages`, `tools`
   - 可修改: `messages`, `tools`
   - 若返回 `stop=True`，调用方要求 `data["response"]` 存在，并直接使用该 response 跳过 LLM 调用

2. **`llm.after_chat`** — LLM 响应后触发
   - 入参: `response`
   - 可修改: `response`
   - `stop=True` 仅停止其他 after_chat handler，不跳过后续 Agent 逻辑

示例调用语义：

```python
before = await self.hooks.emit("llm.before_chat", messages=messages, tools=tools)
if before and before.data:
    messages = before.data.get("messages", messages)
    tools = before.data.get("tools", tools)
    if before.stop:
        response = before.data["response"]
    else:
        response = await self._provider.get_response(self, messages, tools or None)
else:
    response = await self._provider.get_response(self, messages, tools or None)

after = await self.hooks.emit("llm.after_chat", response=response)
if after and after.data:
    response = after.data.get("response", response)
```

### 3.7 受影响文件

| 文件 | 改动 |
|------|------|
| `merco/hooks/registry.py` | 新增 HookResult，升级 emit() |
| `merco/hooks/__init__.py` | 导出 HookResult |
| `merco/core/agent.py` | _agent_loop() 新增 `llm.before_chat` 和 `llm.after_chat` |
| `tests/hooks/test_registry.py` 或 `tests/hooks/test_hook_result.py` | HookResult 单元测试 |
| `tests/integration/test_llm_hooks.py` | Agent LLM hook 集成测试 |

---

## 3.1-3.6 插件迁移（3.7 完成后逐个做）

### 通用迁移模式

每个子系统迁移遵循同一模式：

```
1. PluginContext 添加该子系统属性（默认 None）
2. 新建 Plugin 类，在 activate() 中创建子系统并赋值到 ctx
3. Agent 删除硬初始化代码，改用 property 代理到 ctx
4. Agent 注册该 Plugin
5. TDD: RED → GREEN → REFACTOR
```

### 核心时序约束

后续 3.1-3.6 迁移不能依赖当前 `Agent.__init__` 中的 fire-and-forget 激活方式：

```python
asyncio.ensure_future(self.plugin_manager.activate_all())
```

原因：Observability、MCP、SubAgent 等会成为 Agent 运行所需的核心属性，若激活被后台调度，Agent 可能在插件完成前访问 `self.observer` / `self.mcp_manager` / `self.todo_manager`。

因此 3.1 开始必须先明确「核心内置插件」激活策略：
- 在同步 `Agent.__init__` 中必须完成所有核心内置插件的初始化，不能后台 fire-and-forget。
- 如果当前存在 running event loop，不能用 `run_until_complete()`；需要引入明确的 Agent async factory，或保持核心服务同步构造、仅把扩展注册逻辑放到 async activate。
- 迁移实施计划必须先解决这个时序问题，再移动 Observer 等必需属性。

### 3.1 ObservabilityPlugin

```python
class ObservabilityPlugin(Plugin):
    name = "observability"

    async def activate(self, ctx):
        from merco.observability.observer import Observer
        ctx.observer = Observer(ctx.hooks)
```

注意：当前 `_restore_context()` 会调用 `self.observer.restore(...)`。迁移时必须保证 ObservabilityPlugin 在 `_restore_context()` 之前完成激活，或将 restore 延后到 observer 创建之后。

### 3.2 SkillPlugin

```python
class SkillPlugin(Plugin):
    name = "skills"

    async def activate(self, ctx):
        from merco.skills.registry import SkillRegistry
        registry = SkillRegistry()
        if ctx.config.skills_paths:
            registry.load_from_paths(ctx.config.skills_paths)
        ctx.skill_registry = registry
```

### 3.3 MCPPlugin

```python
class MCPPlugin(Plugin):
    name = "mcp"

    async def activate(self, ctx):
        from merco.mcp.manager import MCPServerManager
        ctx.mcp_manager = MCPServerManager(
            tool_registry=ctx.tool_registry,
            hooks=ctx.hooks,
        )
```

注意：`CloseMCPConnections` 通过 Agent 访问 mcp_manager。迁移时要保持 `agent.mcp_manager` property 兼容。

### 3.4 SubAgentPlugin

```python
class SubAgentPlugin(Plugin):
    name = "subagent"

    async def activate(self, ctx):
        from merco.todo.manager import TodoManager
        from merco.agents.subagent import SubAgentManager

        ctx.todo_manager = TodoManager(f"{ctx.config.memory_path}/../todos.db")
        ctx.sub_agent_manager = SubAgentManager(ctx.agent, ctx.agent_profiles)

        task_tool = ctx.tool_registry.get("task")
        if task_tool:
            task_tool._todo_manager = ctx.todo_manager
            task_tool._sub_agent_manager = ctx.sub_agent_manager
```

注意：PluginContext 应提供明确的 `agent` 引用，而不是隐式 `_agent` 私有属性。该引用只给确实需要 parent Agent 的内置插件使用。

### 3.5 WebPlugin

```python
class WebPlugin(Plugin):
    name = "web"

    async def activate(self, ctx):
        from merco.tools.web_tools import WebFetch, WebSearch
        ctx.register_tool(WebFetch())
        ctx.register_tool(WebSearch())
```

`merco/tools/web_tools.py` 底部自注册代码移除，避免导入模块时产生副作用。

### 3.6 SchedulerPlugin

```python
class SchedulerPlugin(Plugin):
    name = "scheduler"

    def __init__(self):
        self._task = None
        self._scheduler = None

    async def activate(self, ctx):
        from merco.scheduler.cron import CronScheduler
        self._scheduler = CronScheduler()
        ctx.scheduler = self._scheduler
        ctx.hooks.on("agent.start", self._ensure_started)

    async def deactivate(self):
        if self._scheduler:
            await self._scheduler.stop()
        if self._task:
            self._task.cancel()

    async def _ensure_started(self, **kwargs):
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._scheduler.start())
```

注意：不要在 activate() 中无条件 `create_task()`，因为 activate() 可能在临时 event loop 中运行；临时 loop 关闭会留下悬空 task。应在实际 agent.start 生命周期中启动。

---

## 测试策略

### 3.7 测试

- `test_hook_result_stop_stops_later_handlers` — HookResult(stop=True) 阻止后续 handler
- `test_hook_result_data_visible_to_later_handlers` — data 被后续 handler 可见
- `test_emit_returns_merged_data_for_data_only_result` — data-only 修改最终可被调用方读取
- `test_hook_result_backward_compatible_none_handlers` — 现有 handler 不受影响
- `test_emit_returns_none_for_no_handlers_or_no_changes` — 无修改返回 None
- `test_emit_handler_error_isolated` — handler 异常不影响其他 handler
- `test_emit_awaits_callable_returning_coroutine` — callable object 返回 coroutine 也可 await
- `test_llm_before_chat_can_modify_messages_and_tools` — 插件可修改 LLM 请求
- `test_llm_before_chat_can_short_circuit_with_response` — before_chat 可提供 response 跳过 LLM
- `test_llm_after_chat_can_replace_response` — after_chat 可替换 LLM 响应

### 3.1-3.6 测试

- 每个 Plugin 激活后 ctx 有对应子系统
- 插件可被禁用 (config.plugins)
- 子系统在插件未激活时为 None 或 property 明确报错
- 关键 Agent property 保持向后兼容：`agent.observer`, `agent.skill_registry`, `agent.mcp_manager`, `agent.todo_manager`, `agent.sub_agent_manager`
- 集成测试确认 Agent 正常运行

---

## 实施顺序

```
3.7 HookRegistry 升级
  ↓
解决核心内置插件同步激活时序
  ↓
3.1 ObservabilityPlugin
  ↓
3.2 SkillPlugin
  ↓
3.3 MCPPlugin
  ↓
3.4 SubAgentPlugin
  ↓
3.5 WebPlugin
  ↓
3.6 SchedulerPlugin
```

## 自审结论

本 spec 已明确：
- HookResult 的数据合并语义
- stop 的边界（停止 hook 链，不自动停止业务流程）
- data-only 修改不会被 emit() 吞掉
- before_chat / after_chat 的调用方消费方式
- 后续插件迁移的核心时序风险
- SchedulerPlugin 不能在临时 event loop 中启动后台任务

仍需在 implementation plan 中细化：3.1 前如何重构 Agent 初始化时序。该问题不影响先做 3.7，但会影响后续插件迁移。
