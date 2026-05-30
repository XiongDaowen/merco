# Dashboard after MCP — 实现计划

**Goal:** MCP 在 Dashboard 之前加载，工具数目在首页面板内。

## Task 1: 重构 _setup_agent → 构建但不打印

| 文件 | 改动 |
|------|------|
| `cli/main.py` L221-225 | 删除 `console.print(Panel(...))`。改为返回 `(agent, dashboard_text)` |
| `cli/main.py` `main_callback` | 解包 `agent, dashboard_text`，传入 `run_repl()` |
| `cli/main.py` `run_cmd` | 同上 |

## Task 2: run_repl 先 MCP 再 Dashboard

| 文件 | 改动 |
|------|------|
| `cli/main.py` `run_repl(agent, dashboard_text=None)` | 接收参数。MCP 加载后 + 删除独立 MCP 行，换 `console.print(Panel(dashboard_text, title="🚀 Mercury Code"))` |

## 验证

```bash
merco  # Dashboard 应在 MCP 加载日志之后出现
```
