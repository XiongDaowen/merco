# MCP emit await 修复 — spec + plan

单任务，3 处加 `await`。

## 根因

`HookRegistry.emit` 是 `async def`。manager.py 3 处调用缺少 `await`。

## 改动

| 文件 | 行 | 改法 |
|------|-----|------|
| `merco/mcp/manager.py` L66 | `self._hooks.emit(...)` | `await self._hooks.emit(...)` |
| `merco/mcp/manager.py` L120 | `self._hooks.emit("mcp.tool_call", ...)` | `await self._hooks.emit("mcp.tool_call", ...)` |
| `merco/mcp/manager.py` L126 | `self._hooks.emit("mcp.error", ...)` | `await self._hooks.emit("mcp.error", ...)` |

## 验证

```bash
uv run python -c "import merco.mcp.manager; print('OK')"
uv run pytest tests/mcp/ -v
```
