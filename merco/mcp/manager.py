"""MCP Server lifecycle manager — connect, discover tools, register."""
import asyncio
import logging
import time
from .config import MCPServerConfig
from .tool import MCPServerTool

logger = logging.getLogger("merco.mcp")

# Optional mcp imports
_MCP_AVAILABLE = False
try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    _MCP_AVAILABLE = True
except ImportError:
    pass


class MCPServerManager:
    def __init__(self, tool_registry, hooks=None):
        self._registry = tool_registry
        self._hooks = hooks
        self._servers: dict[str, dict] = {}  # name → {config, tools: [MCPServerTool]}
        self._original_config: dict = {}

    async def load_config(self, servers_config: dict) -> None:
        """Load config from merco.json. Connect enabled, skip if already connected."""
        self._original_config = servers_config
        if not _MCP_AVAILABLE:
            logger.warning("mcp package not installed — skipping MCP")
            return
        for name, data in servers_config.items():
            if name in self._servers:
                continue
            cfg = MCPServerConfig.from_dict(name, data)
            if not cfg.enabled:
                continue
            await self.connect(name, cfg)

    async def connect(self, name: str, config: MCPServerConfig) -> bool:
        """Connect to MCP server + discover tools + register them."""
        if not _MCP_AVAILABLE:
            return False
        try:
            if config.command:
                tools = await self._connect_stdio(config)
            elif config.url:
                tools = await self._connect_http(config)
            else:
                logger.warning("MCP '%s': no command or url", name)
                return False

            # Unregister old tools if reconnecting
            await self._unregister_tools(name)

            # Register each tool
            server_tools = []
            for spec in tools:
                tool = MCPServerTool(spec, name, self._call_tool)
                self._registry.register(tool)
                server_tools.append(tool)

            self._servers[name] = {"config": config, "tools": server_tools}
            if self._hooks:
                await self._hooks.emit("mcp.connect", server=name, tools=len(tools))
            logger.info("MCP '%s': %d tools registered", name, len(tools))
            return True
        except Exception as e:
            logger.warning("MCP '%s' connection failed: %s", name, e)
            return False

    async def _connect_stdio(self, config: MCPServerConfig) -> list[dict]:
        params = StdioServerParameters(
            command=config.command, args=config.args, env=config.env
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.list_tools()
                return [t.model_dump() for t in result.tools]

    async def _connect_http(self, config: MCPServerConfig) -> list[dict]:
        # StreamableHTTP support — use mcp.client.streamable_http if available
        try:
            from mcp.client.streamable_http import streamablehttp_client
        except ImportError:
            raise ImportError("mcp HTTP transport requires mcp>=1.0 with streamable_http")
        async with streamablehttp_client(config.url, headers=config.headers) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.list_tools()
                return [t.model_dump() for t in result.tools]

    async def _unregister_tools(self, name: str) -> None:
        if name in self._servers:
            for tool in self._servers[name]["tools"]:
                self._registry.unregister(tool.name)

    async def disconnect(self, name: str) -> None:
        await self._unregister_tools(name)
        self._servers.pop(name, None)

    async def shutdown(self):
        """关闭所有 MCP 连接。"""
        for name in list(self._servers.keys()):
            await self.disconnect(name)

    async def reload(self) -> None:
        for name in list(self._servers.keys()):
            await self.disconnect(name)
        await self.load_config(self._original_config)

    async def _call_tool(self, tool_name: str, arguments: dict) -> dict:
        # Find which server owns this tool, call via MCP session
        for name, state in self._servers.items():
            for tool in state["tools"]:
                if tool.name == tool_name:
                    t0 = time.monotonic()
                    try:
                        if state["config"].command:
                            result = await self._call_stdio_tool(state["config"], tool_name, arguments)
                        else:
                            result = await self._call_http_tool(state["config"], tool_name, arguments)
                        if self._hooks:
                            await self._hooks.emit("mcp.tool_call", server=name, tool=tool_name,
                                                duration=time.monotonic()-t0)
                        return result
                    except Exception as e:
                        if self._hooks:
                            await self._hooks.emit("mcp.error", server=name, tool=tool_name, error=str(e))
                        raise
        return {"error": f"Tool '{tool_name}' not found in any MCP server", "isError": True}

    async def _call_stdio_tool(self, config: MCPServerConfig, tool_name: str, arguments: dict) -> dict:
        params = StdioServerParameters(
            command=config.command, args=config.args, env=config.env
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(tool_name, arguments)
                return result.model_dump()

    async def _call_http_tool(self, config: MCPServerConfig, tool_name: str, arguments: dict) -> dict:
        try:
            from mcp.client.streamable_http import streamablehttp_client
        except ImportError:
            raise ImportError("mcp HTTP transport requires mcp>=1.0 with streamable_http")
        async with streamablehttp_client(config.url, headers=config.headers) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(tool_name, arguments)
                return result.model_dump()

    def status(self) -> dict:
        return {
            name: {
                "connected": True,
                "tools_count": len(state["tools"]),
                "enabled": state["config"].enabled,
            }
            for name, state in self._servers.items()
        }
