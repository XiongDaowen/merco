# MCP HookRegistry 集成 — 设计规格 + 计划

> 单任务，4 行改动。MCPServerManager 用 HookRegistry 替代 Observer 直接调用。

## 动机

MCPServerManager 调用 `self._observer.emit(...)` 但 Observer 无 `emit` 方法。Agent 已通过 `self.hooks.emit("llm.chat")` 发事件给 Observer 订阅。MCP 应用同一条通道。

## 方案

`__init__` 参数 `observer` → `hooks`。内部 `self._hooks.emit(...)` 替代 `self._observer.emit(...)`。

## 改动

| 文件 | 改动 |
|------|------|
| `merco/mcp/manager.py` | `__init__` 参数更名；3 处 emit 从 `_observer` → `_hooks` |
| `merco/core/agent.py` | 调用处 `observer=` → `hooks=` |
| `tests/mcp/test_manager.py` | mock 对应更新 |

## 验证

```bash
uv run python -c "import merco.core.agent; import merco.mcp.manager; print('OK')"
uv run pytest tests/mcp/ -v
```
