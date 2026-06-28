"""Web plugin — registers web tools."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from merco.plugins.base import Plugin

if TYPE_CHECKING:
    from merco.plugins.base import PluginContext

logger = logging.getLogger("merco.plugins.web")


class WebPlugin(Plugin):
    """Registers WebFetch and WebSearch tools."""

    name = "web"
    version = "1.0.0"
    description = "Registers web tools (fetch and search)"

    async def activate(self, ctx: "PluginContext") -> None:
        from merco.tools.web_tools import WebFetch, WebSearch

        ctx.register_tool(WebFetch())
        ctx.register_tool(WebSearch())

        logger.info("Web plugin activated")
