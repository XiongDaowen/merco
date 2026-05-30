# MCP 客户端 — 实现计划

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** 原生 MCP 客户端：配置驱动 + 热重载 + ToolRegistry 注册 + Observer 监控。

**Architecture:** MCPServerManager 管理 server 生命周期 → 工具注册到 ToolRegistry（toolset="mcp:{name}"）→ ToolGuard 保护 → Observer 事件。

**Tech Stack:** Python 3.12+, `mcp` 包, asyncio, ToolRegistry, Observer, ToolGuard

---

### Task 1: MCPServerConfig + config.py 集成

**Objective:** 定义 MCPServerConfig dataclass，在 MercoConfig 加 mcp_servers 段。

**Files:**
- Create: `merco/mcp/__init__.py`
- Create: `merco/mcp/config.py`
- Modify: `merco/core/config.py`
- Test: `tests/unit/test_config.py` (追加)

**Step 1: 写 `merco/mcp/config.py`**

```python
"""MCP server configuration dataclass."""
from dataclasses import dataclass, field

@dataclass
class MCPServerConfig:
    name: str
    command: str | None = None       # stdio transport
    args: list[str] = field(default_factory=list)
    url: str | None = None            # HTTP transport
    headers: dict = field(default_factory=dict)
    env: dict = field(default_factory=dict)
    enabled: bool = True
    timeout: int = 30
    connect_timeout: int = 10
    sandbox: str = "ask"              # ask | deny | allow
    sandbox_rules: list = field(default_factory=list)

    @classmethod
    def from_dict(cls, name: str, data: dict) -> "MCPServerConfig":
        return cls(
            name=name,
            command=data.get("command"),
            args=data.get("args", []),
            url=data.get("url"),
            headers=data.get("headers", {}),
            env=data.get("env", {}),
            enabled=data.get("enabled", True),
            timeout=data.get("timeout", 30),
            connect_timeout=data.get("connect_timeout", 10),
            sandbox=data.get("sandbox", "ask"),
            sandbox_rules=data.get("sandbox_rules", []),
        )
```

**Step 2: MercoConfig 加 mcp_servers**

```python
# config.py — dataclass 加字段
mcp_servers: dict = field(default_factory=dict)

# _to_dict 输出 mcp_servers
# _from_dict 读取 data.get("mcp_servers", {})
```

**Step 3: 测试 + Commit**

```bash
uv run pytest tests/unit/test_config.py -v
git commit -m "feat(mcp): MCPServerConfig dataclass + MercoConfig.mcp_servers"
```

---

### Task 2: MCPServerTool — ToolRegistry 适配器

**Objective:** 实现 `MCPServerTool` 子类，把 MCP tool 适配到 merco 的 BaseTool 协议。

**Files:**
- Create: `merco/mcp/tool.py`
- Test: `tests/mcp/test_tool.py`

**Step 1: 实现**

```python
"""MCP tool → BaseTool adapter"""
import json
from merco.tools.base import BaseTool

class MCPServerTool(BaseTool):
    """将 MCP tool spec 适配为 merco ToolRegistry 的工具"""

    def __init__(self, mcp_spec: dict, server_name: str, handler):
        self.name = mcp_spec["name"]           # MCP 原名
        self.description = mcp_spec.get("description", f"MCP tool from {server_name}")
        self.toolset = f"mcp:{server_name}"
        self.server = server_name
        self._mcp_input_schema = mcp_spec.get("inputSchema", {})
        self._handler = handler  # async callable(tool_name, arguments) -> dict

    @property
    def parameters(self) -> dict:
        return self._mcp_input_schema

    async def execute(self, **kwargs) -> dict:
        try:
            return await self._handler(self.name, kwargs)
        except Exception as e:
            return {"error": str(e), "isError": True}

    def check(self) -> bool:
        return True  # MCP server 已连接

    def get_definition(self, context=None) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self._mcp_input_schema,
            },
        }
```

**Step 2: 测试（mock handler）**

```python
def test_mcp_tool_adapter():
    spec = {"name": "list_issues", "description": "list github issues", "inputSchema": {...}}
    tool = MCPServerTool(spec, "github", mock_handler)
    assert tool.name == "list_issues"
    assert tool.toolset == "mcp:github"
```

**Step 3: Commit**

```bash
git commit -m "feat(mcp): MCPServerTool — adapt MCP tools to ToolRegistry"
```

---

### Task 3: MCPServerManager — 连接管理 + 工具发现

**Objective:** 实现 Manager 核心：connect/disconnect/reload/status。用 `mcp` SDK 做 stdio + HTTP 连接。

**Files:**
- Create: `merco/mcp/manager.py`
- Test: `tests/mcp/test_manager.py`

**Step 1: 实现骨架**

```python
"""MCP Server lifecycle manager"""
import asyncio
import logging
from .config import MCPServerConfig
from .tool import MCPServerTool

logger = logging.getLogger("merco.mcp")

class MCPServerManager:
    def __init__(self, tool_registry, observer=None, guard=None):
        self._servers: dict[str, dict] = {}  # name → {config, session, tools}
        self._registry = tool_registry
        self._observer = observer
        self._guard = guard

    async def load_config(self, servers_config: dict) -> None:
        """Load from merco.json format. Connect enabled servers."""
        for name, data in servers_config.items():
            if name in self._servers:
                continue  # already connected, skip
            cfg = MCPServerConfig.from_dict(name, data)
            if not cfg.enabled:
                continue
            await self.connect(name, cfg)

    async def connect(self, name: str, config: MCPServerConfig) -> bool:
        """Connect to MCP server, discover tools, register them."""
        try:
            # 1. create transport (stdio or HTTP)
            # 2. init MCP session
            # 3. list_tools()
            # 4. register each tool via MCPServerTool
            # 5. store state, emit observer event
            return True
        except Exception as e:
            logger.warning("MCP server '%s' connection failed: %s", name, e)
            if self._observer:
                self._observer.emit("mcp.error", server=name, error=str(e))
            return False

    async def disconnect(self, name: str) -> None:
        """Disconnect and unregister tools."""

    async def reload(self) -> None:
        """Disconnect all, then reload from original config."""

    async def call_tool(self, server: str, tool_name: str, arguments: dict) -> dict:
        """Execute an MCP tool call."""

    def status(self) -> dict:
        """Return per-server status."""
```

**Step 2: 实现 mcp SDK 调用（stdio 传输）**

```python
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def _connect_stdio(self, name: str, cfg: MCPServerConfig) -> list[dict]:
    params = StdioServerParameters(command=cfg.command, args=cfg.args, env=cfg.env)
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            return [t.model_dump() for t in tools.tools]
```

**Step 3: 测试 + Commit**

```bash
git commit -m "feat(mcp): MCPServerManager — connect/discover/register lifecycle"
```

---

### Task 4: ToolGuard 沙箱集成

**Objective:** MCP 工具执行前走 ToolGuard 检查，按 server/tool 粒度控制。

**Files:**
- Modify: `merco/mcp/manager.py`
- Modify: `merco/mcp/tool.py`

**Step 1: MCPServerTool.execute 加 guard**

```python
async def execute(self, **kwargs) -> dict:
    # ToolGuard 检查
    if self._guard:
        approved = await self._guard.check(
            self.name, kwargs,
            source=f"mcp:{self.server}"
        )
        if not approved:
            return {"error": "操作已被拦截或取消"}
    return await self._handler(self.name, kwargs)
```

**Step 2: Commit**

```bash
git commit -m "feat(mcp): ToolGuard integration for MCP tools"
```

---

### Task 5: Observer 事件 + /reload-mcp /mcp-status

**Objective:** MCP 事件接入 Observer。加两个 REPL 命令。

**Files:**
- Modify: `merco/mcp/manager.py` (Observer emit)
- Modify: `cli/commands.py` (两个命令)

**Step 1: manager 加 observer hooks**

```python
# connect 成功:
self._observer.emit("mcp.connect", server=name, tools=len(tools))
# tool call:
self._observer.emit("mcp.tool_call", server=server, tool=tool_name, duration=duration)
# error:
self._observer.emit("mcp.error", server=name, error=str(e))
```

**Step 2: CLI 命令**

```python
@cmd_registry.register("/reload-mcp", desc="重新加载 MCP 服务器", group="info")
async def cmd_reload_mcp(agent, args):
    await agent.mcp_manager.reload()
    console.print(f"[green]MCP 已重载: {len(agent.mcp_manager.status())} servers[/green]")
    return True

@cmd_registry.register("/mcp-status", desc="MCP 服务器状态", group="info")
async def cmd_mcp_status(agent, args):
    for name, s in agent.mcp_manager.status().items():
        icon = "🟢" if s["connected"] else "🔴"
        console.print(f"  {icon} {name}: {s['tools_count']} tools {s.get('error', '')}")
    return True
```

**Step 3: Commit**

```bash
git commit -m "feat(mcp): Observer events + /reload-mcp + /mcp-status"
```

---

### Task 6: Agent 集成 — 启动时加载 MCP

**Objective:** Agent.__init__ 初始化 MCPServerManager，从 config 加载。

**Files:**
- Modify: `merco/core/agent.py`

**Step 1: Agent.__init__ 加 MCP 初始化**

```python
# ── MCP 客户端 ──
from merco.mcp.manager import MCPServerManager
self.mcp_manager = MCPServerManager(
    tool_registry=self.tool_registry,
    observer=self.observer,
    guard=None,  # ToolGuard per-tool check handles this
)
# 不在这里 await — 在 run() 首次调用时懒加载，或通过 /reload-mcp 触发
```

**Step 2: Commit**

```bash
git commit -m "feat(mcp): integrate MCPServerManager into Agent"
```

---

## Task Order

```
Task 1: MCPServerConfig      ← 无依赖
Task 2: MCPServerTool        ← 无依赖
Task 3: MCPServerManager     ← 依赖 1+2
Task 4: ToolGuard 集成       ← 依赖 2+3
Task 5: Observer + CLI       ← 依赖 3
Task 6: Agent 集成           ← 依赖 3
```
