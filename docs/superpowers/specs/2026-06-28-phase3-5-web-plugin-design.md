# Phase 3.5：WebPlugin 设计规格

> 日期: 2026-06-28
> 基于: `docs/project-vision/references/architecture-refactor-plan.md`
> 前置: Phase 3.1-3.4 已完成

## 背景

`merco/tools/web_tools.py` 底部有模块级自注册：

```python
from .registry import tool_registry
tool_registry.register(WebFetch())
tool_registry.register(WebSearch())
```

这是一个典型的 import-time 副作用。当模块被导入时自动注册工具，调用方无法控制是否注册或何时注册。

3.5 目标很简单：把 WebFetch/WebSearch 的注册从模块 import-time 副作用迁移到 WebPlugin。

## 目标

1. 新增 `WebPlugin`，在 `activate(ctx)` 中注册 WebFetch 和 WebSearch 工具。
2. 移除 `merco/tools/web_tools.py` 底部自注册代码。
3. 在 `Agent.create(...)` + `_initialize_async_plugins()` 中注册并激活 WebPlugin。
4. 网络工具仍通过 `merco/tools/web_tools.py` 暴露（作为数据结构模块），只移除副作用。

## 非目标

- 不改变 WebFetch/WebSearch 执行逻辑。
- 不改工具参数或实现。
- 不迁移 Scheduler。
- 不添加新的网络工具。

---

## 设计

### 1. WebPlugin

新增 `merco/plugins/builtin/web/plugin.py`：

```python
class WebPlugin(Plugin):
    name = "web"
    version = "1.0.0"
    description = "Registers web tools (fetch and search)"

    async def activate(self, ctx):
        from merco.tools.web_tools import WebFetch, WebSearch
        ctx.register_tool(WebFetch())
        ctx.register_tool(WebSearch())
```

不需要同步到 `ctx.agent`，因为工具注册到 `ctx.tool_registry` 就全局可见。

### 2. web_tools.py 修改

删除底部两行：

```python
from .registry import tool_registry  # noqa: E402 — 模块末尾自注册
tool_registry.register(WebFetch())
tool_registry.register(WebSearch())
```

### 3. Agent 初始化

- 注册 `WebPlugin`
- `_initialize_async_plugins()` 在 `subagent` 之后、`activate_all()` 之前激活 `web`

### 4. 激活顺序

```text
observability → restore → skills → mcp → subagent → web → activate_all
```

---

## 测试策略

### WebPlugin 单元测试

- `WebPlugin.activate(ctx)` 后 `ctx.tool_registry.get("web_fetch")` 非 None
- `ctx.tool_registry.get("web_search")` 非 None
- metadata: name/version/description 稳定

### 回归测试

- `tests/tools/`
- `tests/integration/test_agent_loop.py`
- `tests/cli/test_cli_help.py`
- `tests/plugins/`

## 风险

- 如果其他代码依赖 `import web_tools` 自动注册（模块 import-time 副作用），迁移后不再注册。需确认所有调用方都通过 ToolRegistry 获取工具，而非依赖 import 副作用。
- 现有 `merco/tools/__init__.py` 中的 `discover_tools()` 可能导入 `web_tools` 以触发自注册，迁移后无效应。需检查。

## 用户确认的设计选择

- 3.5 范围：**仅工具注册迁移**。