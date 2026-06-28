# Phase 3.2：SkillPlugin 彻底迁移设计规格

> 日期: 2026-06-28
> 基于: `docs/project-vision/references/architecture-refactor-plan.md`
> 前置: Phase 3.1 ObservabilityPlugin + Agent.create async factory 已完成

## 背景

当前技能系统仍由 `Agent.__init__(..., skill_registry=None)` 接收外部注入，并直接设置：

```python
self.skill_registry = skill_registry
```

同时：

- `SkillsHintChunk` 通过 `agent.skill_registry` 注入相关 skill 内容到 system prompt。
- `SkillViewTool` 需要调用 `set_skill_registry(registry)` 才能列出和加载技能。
- `SkillRegistry.load_from_paths(config.skills_paths)` 已存在，但当前不由插件统一负责。

用户选择 3.2 采用**彻底迁移**：不保留“构造参数是主路径”的双来源，而是让 SkillPlugin 成为技能系统唯一初始化入口。

## 目标

1. 新增 `SkillPlugin`，负责创建并加载 `SkillRegistry`。
2. `PluginContext` 增加 `agent` 与 `skill_registry`。
3. `SkillPlugin.activate(ctx)` 同步：
   - `ctx.skill_registry`
   - `ctx.agent.skill_registry`
   - `SkillViewTool` 的 registry 注入
4. `Agent.create(...)` 激活 `skills` 插件。
5. 生产内部 Agent 创建路径迁移到 `Agent.create(...)`。
6. 移除 `Agent.__init__(skill_registry=...)` 作为初始化入口。
7. 保持 `SkillsHintChunk` 和 `SkillViewTool` 现有行为不变，只改变 registry 来源。

## 非目标

- 不迁移 MCP / Web / Scheduler。
- 不改变 skill 文件格式、SkillLoader 解析逻辑、SkillRegistry 匹配逻辑。
- 不重写 `SkillViewTool`，仅通过现有 `set_skill_registry()` 注入。
- 不改 `SkillsHintChunk` 的匹配算法。
- 不把全测试套件里的同步 `test_agent` fixture 全部改成 async；这是测试基础设施大迁移，单独处理。

---

## 设计

### 1. SkillPlugin

新增文件：`merco/plugins/builtin/skills/plugin.py`

```python
class SkillPlugin(Plugin):
    name = "skills"
    version = "1.0.0"
    description = "Loads skills and injects the skill registry"

    async def activate(self, ctx):
        from merco.skills.registry import SkillRegistry

        registry = SkillRegistry()
        registry.load_from_paths(ctx.config.skills_paths)

        ctx.skill_registry = registry
        if ctx.agent is not None:
            ctx.agent.skill_registry = registry

        skill_tool = ctx.tool_registry.get("skill_view")
        if skill_tool and hasattr(skill_tool, "set_skill_registry"):
            skill_tool.set_skill_registry(registry)
```

### 2. PluginContext 扩展

`PluginContext.__init__` 新增：

```python
agent: Agent | None = None
skill_registry: SkillRegistry | None = None
```

原因：

- `SkillPlugin` 需要把 registry 同步到 `agent.skill_registry`，让 `SkillsHintChunk` 保持不变。
- 后续 `SubAgentPlugin` 也需要 `ctx.agent`，提前建立明确引用，避免私有 `_agent`。

### 3. Agent 初始化变化

#### 3.1 `Agent.__init__`

移除 `skill_registry` 参数：

```python
def __init__(self, config: MercoConfig, tool_registry=None, _defer_plugin_init: bool = False):
    self.skill_registry = None
```

也就是说：

- `Agent.__init__` 不再接受外部 registry。
- `agent.skill_registry` 初始为 None。
- `SkillPlugin` 激活后填充。

#### 3.2 `Agent.create(...)`

改为：

```python
@classmethod
async def create(cls, config: MercoConfig, tool_registry=None) -> "Agent":
    agent = cls(config=config, tool_registry=tool_registry, _defer_plugin_init=True)
    await agent._initialize_async_plugins()
    return agent
```

不再接收 `skill_registry` 参数。

### 4. 插件激活顺序

`Agent._initialize_async_plugins()` 顺序：

```text
1. await plugin_manager.activate("observability")
2. sync agent.observer
3. _restore_context()
4. await plugin_manager.activate("skills")
5. await plugin_manager.activate_all()
```

原因：

- `observability` 必须在 `_restore_context()` 前。
- `skills` 依赖基础 tool_registry 和 config，必须在 Agent 运行前。
- `activate_all()` 后续会跳过已 active 的 observability/skills（依赖 3.1 的幂等 activate）。

### 5. 内部调用点迁移

生产内部 Agent 创建点应从：

```python
Agent(config=..., tool_registry=...)
```

迁到：

```python
await Agent.create(config=..., tool_registry=...)
```

本轮重点：

- `SubAgentManager._create_sub_agent`

`SubAgentManager._create_sub_agent` 当前是同步方法，会创建子 Agent。迁移后：

```python
async def _create_sub_agent(...):
    sub_agent = await Agent.create(...)
```

调用方 `dispatch()` 已经是 async，因此可以承接这个变化。

### 6. 测试 fixture 策略

`tests/conftest.py::test_agent` 是大量现有同步测试共享的 legacy fixture。如果强行改成 async fixture，会把无关测试全部牵连进来。

因此本轮采用：

- 保留现有 `test_agent` legacy fixture，用于旧测试兼容。
- 新增 `async_test_agent` fixture 或在新测试中显式 `await Agent.create(...)`。
- 3.2 新功能测试全部覆盖 `Agent.create(...)` factory path。

这不违背“彻底迁移”目标，因为“彻底迁移”指生产初始化入口和技能系统来源，不要求一次性重写测试基础设施。

### 7. Legacy 兼容策略

直接 `Agent(...)` 仍允许创建对象，但：

- 不再接受 `skill_registry` 参数。
- `skill_registry` 初始为 None。
- 不保证 legacy path 自动加载 skills。

内部生产路径应使用 `Agent.create(...)`。

### 8. SkillViewTool 注入

`SkillPlugin` 使用现有 API：

```python
tool = ctx.tool_registry.get("skill_view")
if tool and hasattr(tool, "set_skill_registry"):
    tool.set_skill_registry(registry)
```

不改 `SkillViewTool` 结构。

---

## 测试策略

### SkillPlugin 单元测试

- activate 后 `ctx.skill_registry` 是 `SkillRegistry`
- `ctx.agent.skill_registry` 被同步
- `config.skills_paths` 中的 skill 被加载
- 若 tool_registry 有 `skill_view`，其 `_skill_registry` 被注入
- tool_registry 没有 `skill_view` 时安全跳过

### Agent.create 集成测试

- `agent = await Agent.create(...)` 后 `agent.skill_registry` 非 None
- `SkillsHintChunk` 能通过 `agent.skill_registry` 注入相关 skill
- `skill_view` 工具能看到 registry 并加载 skill
- `Agent.create(...)` 不再接受 `skill_registry` 参数

### SubAgentManager 测试

- 子 agent 通过 `Agent.create()` 创建
- 子 agent 仍应用 profile prompt / model override / max_tool_calls
- `dispatch()` 仍可完成 todo 状态更新

### 回归测试

- `tests/tools/test_*skill*`（如存在）
- `tests/agents/test_subagent.py`
- `tests/agents/test_subagent_profile.py`
- `tests/integration/test_agent_loop.py`
- `tests/plugins/`

---

## 风险与约束

1. **同步到异步边界**
   - `SubAgentManager._create_sub_agent` 需要变成 async。
   - 调用方 `dispatch()` 已是 async，可承接。

2. **legacy Agent(...) 行为变化**
   - 直接 `Agent(...)` 不再接受 `skill_registry` 参数，也不自动加载 skills。
   - 这是彻底迁移的代价；生产内部调用点应迁到 `Agent.create()`。

3. **测试 fixture 暂保留 legacy**
   - 为避免无关测试大迁移，`test_agent` 暂保留 legacy path。
   - 新增测试必须覆盖 factory path。

4. **SkillViewTool 依赖 tool_registry 中已有 skill_view**
   - 如果 tool 不存在，插件应安全跳过，不报错。

5. **重复激活**
   - `observability` 和 `skills` 会先手动激活，再由 `activate_all()` 看到；依赖 PluginManager 幂等。

## 用户确认的设计选择

用户选择：**彻底迁移**。

含义：SkillPlugin 是技能系统唯一初始化入口；生产内部 Agent 创建路径迁移到 `Agent.create()`，不再依赖 `Agent.__init__(skill_registry=...)`。

## 自审结论

已修正：

- 原 spec 把 `tests/conftest.py::test_agent` 纳入“彻底迁移”，会导致大量同步测试被迫改 async，范围爆炸。
- 修正为：生产内部路径彻底迁移；测试 legacy fixture 暂保留；新测试覆盖 factory path。
- 明确 `Agent.__init__` 不再接受 `skill_registry` 参数，避免技能 registry 双来源。
- 明确 `SubAgentManager._create_sub_agent` 是本轮需要迁移的生产内部调用点。
