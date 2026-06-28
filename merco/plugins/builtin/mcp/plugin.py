"""MCP plugin — creates the MCP server manager."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from merco.plugins.base import Plugin

if TYPE_CHECKING:
    from merco.plugins.base import PluginContext

logger = logging.getLogger("merco.plugins.mcp")


class MCPPlugin(Plugin):
    """Creates MCPServerManager and attaches it to PluginContext.

    This plugin performs NO network or stdio I/O. Loading MCP servers
    remains an explicit caller step.
    """

    name = "mcp"
    version = "1.0.0"
    description = "Creates the MCP server manager"

    async def activate(self, ctx: "PluginContext") -> None:
        from merco.mcp.manager import MCPServerManager

        manager = MCPServerManager(
            tool_registry=ctx.tool_registry,
            hooks=ctx.hooks,
        )
        ctx.mcp_manager = manager
        if ctx.agent is not None:
            ctx.agent.mcp_manager = manager

        logger.info("MCP plugin activated")
