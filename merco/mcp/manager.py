"""MCP Server lifecycle manager - connect, discover tools, register."""

import logging
import time
from contextlib import AsyncExitStack

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
        # name -> {config, tools, session, cleanup}
        # session 持久复用跨多次工具调用（不再每次 fork+握手）；cleanup 关闭 session+transport
        self._servers: dict[str, dict] = {}
        self._original_config: dict = {}

    async def load_config(self, servers_config: dict) -> None:
        """Load config from merco.json. Connect enabled, skip if already connected."""
        self._original_config = servers_config
        if not _MCP_AVAILABLE:
            logger.warning("mcp package not installed - skipping MCP")
            return
        for name, data in servers_config.items():
            if name in self._servers:
                continue
            cfg = MCPServerConfig.from_dict(name, data)
            if not cfg.enabled:
                continue
            await self.connect(name, cfg)

    async def connect(self, name: str, config: MCPServerConfig) -> bool:
        """Connect to MCP server + discover tools + register them. Session 持久复用。"""
        if not _MCP_AVAILABLE:
            return False
        try:
            if config.command:
                session, tools, cleanup = await self._connect_stdio(config)
            elif config.url:
                session, tools, cleanup = await self._connect_http(config)
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

            self._servers[name] = {
                "config": config,
                "tools": server_tools,
                "session": session,
                "cleanup": cleanup,
            }
            if self._hooks:
                await self._hooks.emit("mcp.connect", server=name, tools=len(tools))
            logger.info("MCP '%s': %d tools registered", name, len(tools))
            return True
        except Exception as e:
            logger.warning("MCP '%s' connection failed: %s", name, e)
            return False

    async def _connect_stdio(self, config: MCPServerConfig):
        """打开持久 stdio session。返回 (session, tools, cleanup)。

        session 跨多次工具调用复用（旧实现每次调用都 fork+握手+关闭，开销大）；
        cleanup 关闭 session 与 stdio transport（disconnect/shutdown 时调）。
        初始化失败时自动清理已打开的资源。
        """
        params = StdioServerParameters(command=config.command, args=config.args, env=config.env)
        stack = AsyncExitStack()
        try:
            read, write = await stack.enter_async_context(stdio_client(params))
            session = await stack.enter_async_context(ClientSession(read, write))
            await session.initialize()
            result = await session.list_tools()
            tools = [t.model_dump() for t in result.tools]
        except Exception:
            await stack.aclose()
            raise
        return session, tools, stack.aclose

    async def _connect_http(self, config: MCPServerConfig):
        """打开持久 HTTP session。返回 (session, tools, cleanup)。"""
        try:
            from mcp.client.streamable_http import streamablehttp_client
        except ImportError:
            raise ImportError("mcp HTTP transport requires mcp>=1.0 with streamable_http")
        stack = AsyncExitStack()
        try:
            read, write = await stack.enter_async_context(
                streamablehttp_client(config.url, headers=config.headers)
            )
            session = await stack.enter_async_context(ClientSession(read, write))
            await session.initialize()
            result = await session.list_tools()
            tools = [t.model_dump() for t in result.tools]
        except Exception:
            await stack.aclose()
            raise
        return session, tools, stack.aclose

    async def _unregister_tools(self, name: str) -> None:
        if name in self._servers:
            for tool in self._servers[name]["tools"]:
                self._registry.unregister(tool.name)

    async def disconnect(self, name: str) -> None:
        if name not in self._servers:
            return
        await self._unregister_tools(name)
        state = self._servers.pop(name)
        cleanup = state.get("cleanup")
        if cleanup:
            try:
                await cleanup()
            except Exception as e:
                logger.debug("MCP '%s' cleanup error: %s", name, e)

    async def shutdown(self):
        """关闭所有 MCP 连接（含持久 session）。"""
        for name in list(self._servers.keys()):
            await self.disconnect(name)

    async def reload(self) -> None:
        for name in list(self._servers.keys()):
            await self.disconnect(name)
        await self.load_config(self._original_config)

    async def _call_tool(self, tool_name: str, arguments: dict) -> dict:
        # Find which server owns this tool, call via 复用 session
        for name, state in self._servers.items():
            for tool in state["tools"]:
                if tool.name == tool_name:
                    t0 = time.monotonic()
                    try:
                        result = await self._call_with_session(state, tool_name, arguments)
                        if self._hooks:
                            await self._hooks.emit(
                                "mcp.tool_call", server=name, tool=tool_name, duration=time.monotonic() - t0
                            )
                        return result
                    except Exception as e:
                        if self._hooks:
                            await self._hooks.emit("mcp.error", server=name, tool=tool_name, error=str(e))
                        raise
        return {"error": f"Tool '{tool_name}' not found in any MCP server", "isError": True}

    async def _call_with_session(self, state: dict, tool_name: str, arguments: dict) -> dict:
        """用持久 session 调工具；session 死亡（调用抛异常）时重连一次重试。"""
        try:
            result = await state["session"].call_tool(tool_name, arguments)
            return result.model_dump()
        except Exception as e:
            logger.warning(
                "MCP '%s' call '%s' failed (%s), reconnecting once",
                state["config"].name,
                tool_name,
                e,
            )
            await self._reconnect(state)
            result = await state["session"].call_tool(tool_name, arguments)
            return result.model_dump()

    async def _reconnect(self, state: dict) -> None:
        """关闭旧 session，用同 config 重开并替换 state 里的 session/cleanup。"""
        config = state["config"]
        old_cleanup = state.get("cleanup")
        if old_cleanup:
            try:
                await old_cleanup()
            except Exception:
                pass
        if config.command:
            session, _tools, cleanup = await self._connect_stdio(config)
        else:
            session, _tools, cleanup = await self._connect_http(config)
        state["session"] = session
        state["cleanup"] = cleanup

    def status(self) -> dict:
        return {
            name: {
                "connected": True,
                "tools_count": len(state["tools"]),
                "enabled": state["config"].enabled,
            }
            for name, state in self._servers.items()
        }
