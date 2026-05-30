# /tools 过滤 check()=False 的工具

`list_tools()` 返回所有注册工具，包括 `check()=False` 的（task、旧 mcp_call）。`/tools` 应只展示可用工具。

## 改动

`cli/commands.py` cmd_tools: `t.check()` 为 False 的跳过。

```python
tools = [t for t in agent.tool_registry.list_tools() if t.check()] if agent.tool_registry else []
```
