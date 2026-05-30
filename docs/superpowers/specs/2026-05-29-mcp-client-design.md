# MCP 客户端 — 设计规格

> 原生 MCP 客户端：配置驱动 + 热重载 + ToolRegistry 注册 + Observer 监控 + ToolGuard 保护。汲取 Hermes/OpenCode/OpenClaw 三家之长。

## 动机

merco 的 `mcp_tools.py` 是骨架（"not yet configured"），无法接入外部 MCP server。MCP 是 Agent 生态的核心协议，三家参考项目都完整支持。

## 方案选择

**方案 B — MCP 管理器**：对标 OpenCode 的灵活性 + 超 Hermes 的热重载和可观察性。

- `MCPServerManager` 管理每个 server 的完整生命周期
- `/reload-mcp` 热重载，无需重启
- Observer 集成 mcp 状态事件
- ToolGuard 沙箱集成

## 三家对标

| 特性 | Hermes | OpenCode | merco（设计） |
|------|--------|----------|-------------|
| 传输 | stdio + HTTP | local + remote | stdio + HTTP |
| 配置 | `mcp_servers` | discriminated `type` | `mcp_servers` in merco.json |
| 工具命名 | `mcp_{s}_{t}` | 原生 | toolset="mcp:{s}", 原名 |
| 热重载 | ❌ | 开关 | `/reload-mcp` |
| 可观察 | ❌ | ❌ | ✅ Observer 事件 |
| 沙箱 | env 过滤 | — | ✅ ToolGuard 集成 |
| CLI | mcp add/list | inside TUI | `merco mcp add/list/remove/test/status` |

## 架构

```
merco.json mcp_servers
       │
  MCPServerManager
  ├─ connect → mcp.list_tools()
  ├─ 注册到 ToolRegistry（toolset="mcp:{name}"）
  ├─ Observer.emit("mcp.status")
  └─ ToolGuard 权限检查
```

## 配置

```json
{
  "mcp_servers": {
    "github": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": {"GITHUB_TOKEN": "ghp_xxx"},
      "enabled": true,
      "timeout": 30
    },
    "filesystem": {
      "url": "http://localhost:8808/mcp",
      "headers": {"Authorization": "Bearer xxx"},
      "enabled": false
    }
  }
}
```

## 核心组件

### MCPServerConfig

dataclass: name, command/args (stdio) 或 url/headers (HTTP), enabled, timeout, connect_timeout.

### MCPServerManager

- `load_config(servers)` — 幂等加载，启动 enabled server
- `reload()` — 全卸载 + 重新加载
- `connect(name, config)` → 连接 + 发现工具 + 注册
- `disconnect(name)` → 断开 + 注销工具
- `status()` → {name, connected, tools_count, last_error}

### 工具注册

每个 MCP 工具注册到 ToolRegistry：`name=原名`, `toolset="mcp:{server}"`, `server=归属服务器`。调用时走统一的 `_call_mcp_tool` handler。

### ToolGuard 集成

配置 `sandbox: ask/deny/allow` + `sandbox_rules`（pattern + action）。执行前 ToolGuard 检查。

### Observer 事件

`mcp.connect` / `mcp.error` / `mcp.tool_call` — 用量、错误、健康状态可追踪。

## CLI 命令

```bash
merco mcp add    <name> --command/-c ... [--args ...] [--env KEY=VAL]
merco mcp add    <name> --url/-u ... [--headers KEY=VAL]
merco mcp list
merco mcp remove <name>
merco mcp test   <name>       # 测试连接 + 列出工具
merco mcp status              # 全部 server 状态
```

REPL 内：`/reload-mcp`、`/mcp-status`。

## 错误处理

| 层 | 错误 | 处理 |
|---|------|------|
| 连接失败 | timeout / command not found | `{error, suggestion}` |
| 工具调用失败 | MCP 协议错误 | 透传 `isError: true` |
| 工具不存在 | Registry miss | `{error, available_tools}` |
| 超时 | 超过 timeout | `{error, suggestion}` |

复用 `self_healing.tool_error()` 生成结构化错误。

## 依赖

- `mcp` Python 包（>=1.0.0，可选依赖，未安装时跳过 MCP 支持）
- Python 3.12+ asyncio

## 改动文件

| 文件 | 改动 |
|------|------|
| `merco/mcp/__init__.py` | **新建** |
| `merco/mcp/manager.py` | **新建**：MCPServerManager |
| `merco/mcp/config.py` | **新建**：MCPServerConfig |
| `merco/mcp/tool.py` | **新建**：MCPServerTool（适配 ToolRegistry） |
| `merco/core/config.py` | 加 `mcp_servers` 配置段 |
| `merco/tools/mcp_tools.py` | 重写：接入 MCPServerManager |
| `cli/main.py` | 加 `/reload-mcp`、`/mcp-status` 命令 |
| `cli/commands.py` | 加两个命令 handler |
| `pyproject.toml` | 加 `mcp` 可选依赖 |
