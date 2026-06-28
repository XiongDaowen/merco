# Phase 3.3：MCPPlugin 设计规格

> 日期: 2026-06-28
> 基于: `docs/project-vision/references/architecture-refactor-plan.md`
> 前置: Phase 3.1 ObservabilityPlugin + Phase 3.2 SkillPlugin 已完成

## 背景

当前 `Agent.__init__` 直接创建 `MCPServerManager`：

```python
from merco.mcp.manager import MCPServerManager
self.mcp_manager = MCPServerManager(
    tool_registry=self.tool_registry,
    hooks=self.hooks,
)
```

`MCPServerManager` 在 `merco.core.interrupt.CloseMCPConnections` 中被引用：

```python
if ctx.agent.mcp_manager:
    await ctx.agent.mcp_manager.shutdown()
```

`MCPServerManager` 还涉及网络/stdio I/O（`load_config`、`connect`、`shutdown`），这使它与 3.1 的 Observer、3.2 的 Skill 不同：不应在插件激活过程中跑 I/O。

用户要求 3.3 设计为“健壮 + 架构干净”。本设计遵循该原则：MCPPlugin 只负责依赖组装，不在激活中触发 I/O。

## 目标

1. 新增 `MCPPlugin`，负责创建 `MCPServerManager`。
2. `PluginContext` 增加 `mcp_manager` 字段。
3. `MCPPlugin.activate(ctx)` 同步 `ctx.mcp_manager` 与 `ctx.agent.mcp_manager`。
4. `Agent.create(...)` 激活 `mcp` 插件。
5. `Agent.__init__` 移除 `MCPServerManager` 创建。
6. 保持 `CloseMCPConnections` 兼容（仍读 `agent.mcp_manager`）。

## 非目标

- 不在插件激活过程中调用 `mcp_manager.load_config(...)`。
- 不改 `MCPServerManager` 本身。
- 不改 `CloseMCPConnections` 行为。
- 不迁移 SubAgent / Web / Scheduler。
- 不引入新的 MCP API 接入或传输方式。

---

## 设计

### 1. MCPPlugin

新增文件：`merco/plugins/builtin/mcp/plugin.py`

```python
class MCPPlugin(Plugin):
    name = "mcp"
    version = "1.0.0"
    description = "Creates the MCP server manager"

    async def activate(self, ctx):
        from merco.mcp.manager import MCPServerManager

        manager = MCPServerManager(
            tool_registry=ctx.tool_registry,
            hooks=ctx.hooks,
        )
        ctx.mcp_manager = manager
        if ctx.agent is not None:
            ctx.agent.mcp_manager = manager
```

### 2. PluginContext 扩展

`PluginContext.__init__` 新增：

```python
mcp_manager: MCPServerManager | None = None
```

需要在 `TYPE_CHECKING` 中导入 `MCPServerManager`。

### 3. Agent 初始化变化

#### 3.1 `Agent.__init__`

删除：

```python
from merco.mcp.manager import MCPServerManager
self.mcp_manager = MCPServerManager(
    tool_registry=self.tool_registry,
    hooks=self.hooks,
)
```

替换为：

```python
self.mcp_manager = None
```

#### 3.2 `Agent.create(...)`

`_initialize_async_plugins()` 顺序：

```text
1. await plugin_manager.activate("observability")
2. sync agent.observer
3. _restore_context()
4. await plugin_manager.activate("skills")
5. await plugin_manager.activate("mcp")
6. await plugin_manager.activate_all()
```

#### 3.3 注册 MCPPlugin

```python
self.plugin_manager.register(ObservabilityPlugin())
self.plugin_manager.register(SkillPlugin())
self.plugin_manager.register(MCPPlugin())
self.plugin_manager.register(SuperpowerPlugin())
```

### 4. 中断清理兼容

`CloseMCPConnections` 已存在：

```python
if ctx.agent.mcp_manager:
    await ctx.agent.mcp_manager.shutdown()
```

`agent.mcp_manager` 现在由 MCPPlugin 同步过来。中断路径无需改动。

如果 MCPPlugin 尚未激活，`agent.mcp_manager` 是 None，`if` 判断跳过 `shutdown()`。这是安全路径。

### 5. MCP 加载

`MCPServerManager.load_config(...)` 仍由调用方手动触发。本轮不修改 `Agent.run()`，与当前实现保持一致：

- 当前 `Agent.__init__` 也不会自动 `load_config`，只是构造 manager。
- 加载由 CLI 或测试 fixture 在创建 Agent 之后手动触发。

未来如要自动加载 `config.mcp_servers`，可单独一轮做（同样在 `Agent.run()` 启动后异步调用），不纳入本轮范围。

### 6. legacy 兼容

`Agent(...)` 仍允许创建对象，但 `mcp_manager` 初始为 None。生产内部创建点应继续使用 `Agent.create(...)`，由 MCPPlugin 提供 manager。

---

## 测试策略

### MCPPlugin 单元测试

- `MCPPlugin.activate(ctx)` 后 `ctx.mcp_manager` 是 `MCPServerManager`
- `ctx.agent.mcp_manager` 被同步
- metadata: name/version/description 稳定
- 工具注册表引用一致

### Agent.create 集成测试

- `agent = await Agent.create(...)` 后 `agent.mcp_manager` 是 `MCPServerManager`
- `mcp` 在 `plugin_manager.active_plugins`
- `CloseMCPConnections` 能 `await agent.mcp_manager.shutdown()`

### 回归测试

- `tests/mcp/test_manager.py`
- `tests/core/test_interrupt.py`
- `tests/integration/test_interrupt_flow.py`

注意：`tests/core/test_agent.py::test_agent_has_mcp_manager` 当前断言 `isinstance(test_agent.mcp_manager, MCPServerManager)`，使用 legacy `Agent(...)` 路径。3.3 之后 legacy path `mcp_manager` 是 None，所以这个测试必须**改为覆盖 factory path**：用 `await Agent.create(...)` 断言 `agent.mcp_manager is MCPServerManager`。这是这次迁移必要的测试改动。

---

## 风险与约束

1. **legacy `Agent(...)` 不自动获得 MCPPlugin**
   - `mcp_manager` 是 None。
   - 不破坏现有 legacy 测试，因为 `CloseMCPConnections` 已有 None 检查。

2. **加载 MCP 服务器仍需手动**
   - 不在本轮范围。

3. **中断清理路径**
   - `agent.mcp_manager` 由插件同步赋值为 `MCPServerManager`。
   - `shutdown()` 是 async awaitable，符合现有协议。

4. **重复激活**
   - `observability`、`skills`、`mcp` 全部由 `PluginManager.activate()` 幂等化（3.1 完成）。

## 用户确认的设计选择

用户要求：**健壮 + 架构干净**。

对应实现：**方案 A — 仅创建管理器**，不触发 I/O。保持插件单职责，避免把网络/stdio 失败引入插件激活。