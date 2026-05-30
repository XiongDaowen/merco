# MCP 启动时加载 — spec + plan

单任务。将 MCP 加载从 Agent.run() 移到 CLI REPL 启动阶段。

## 动机

当前 MCP 在第一条消息时才加载（lazy init），第一轮对话用不上 MCP 工具。加载应在 REPL 开始前完成。

## 改动

| 文件 | 改动 |
|------|------|
| `cli/main.py` L407 后 | 在 REPL 循环前加 `await agent.mcp_manager.load_config(agent.config.mcp_servers)` |
| `merco/core/agent.py` L298-300 | 删除 3 行 lazy init：`if self.config.mcp_servers ... await self.mcp_manager.load_config(...)` |

## 验证

```bash
uv run python -c "import merco.core.agent; import cli.main; print('OK')"
```
