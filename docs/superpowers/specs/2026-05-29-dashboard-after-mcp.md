# Dashboard after MCP load — spec

问题：Dashboard 在 MCP 加载前渲染，MCP 工具数不能反映到首页。

方案：把 Dashboard 渲染从 `_setup_agent()` 移出，改为 `_setup_agent()` 构建但不打印。`run_repl()` 先加载 MCP，再渲染 Dashboard。

## 改动

| 文件 | 改动 |
|------|------|
| `cli/main.py` `_setup_agent()` | 删除 `console.print(Panel(...))`，改为 `return agent, dashboard_text` |
| `cli/main.py` `main_callback` / `run_cmd` | 接收 `agent, _` 或适配 |
| `cli/main.py` `run_repl()` | 加 `dashboard_text` 参数。MCP 加载后打印 dashboard，再进入 REPL。同时删除独立的 MCP 工具数行 |

## 不破坏

- `_setup_agent` 仍在 CLI 层，只是分成"构建"和"展示"两步
- Agent 不变
- MCPServerManager 不变
