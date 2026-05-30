# /tools 分组展示 — spec + plan

单任务。CLI /tools 按 toolset 分组展示，统一截断描述。

## 改动

`cli/commands.py` 的 `cmd_tools` handler 替换为分组版：

```python
@cmd_registry.register("/tools", desc="列出可用工具", group="info")
async def cmd_tools(agent, args):
    tools = agent.tool_registry.list_tools() if agent.tool_registry else []
    if not tools:
        console.print("无可用工具")
        return True

    # 按 toolset 分组
    groups: dict[str, list] = {}
    for t in tools:
        groups.setdefault(t.toolset or "builtin", []).append(t)

    console.print("[bold]可用工具:[/bold]")
    for toolset, group_tools in sorted(groups.items()):
        label = f"[mcp:{toolset[4:]}]" if toolset.startswith("mcp:") else "[内置]"
        console.print(f"\n  {label}")
        for t in group_tools:
            desc = (t.description or "")[:60]
            console.print(f"    [bold]{t.name}[/bold]  [dim]{desc}[/dim]")
    return True
```

## 验证

重启 merco，`/tools` 应该看到分组输出。

```bash
uv run python -c "import cli.commands; print('OK')"
```
