# Dashboard MCP 工具数更新 — spec

单行改动。MCP 加载完成后打印一行工具统计。

## 改动

`cli/main.py`，MCP pre-load 代码块后加一行：

```python
# 在 await agent.mcp_manager.load_config(...) 之后
status = agent.mcp_manager.status()
if status:
    parts = [f"{name} ({s['tools_count']})" for name, s in status.items()]
    console.print(f"  MCP: [bold]{', '.join(parts)}[/bold]")
```
