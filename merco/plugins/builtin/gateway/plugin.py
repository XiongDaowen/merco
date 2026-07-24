"""Gateway plugin - registers the built-in WebhookGateway."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from merco.plugins.base import Plugin

if TYPE_CHECKING:
    from merco.plugins.base import PluginContext

logger = logging.getLogger("merco.plugins.gateway")


class GatewayPlugin(Plugin):
    """Registers the built-in WebhookGateway into ctx.gateway_registry."""

    name = "gateway"
    version = "1.0.0"
    description = "Registers the built-in webhook gateway"
    priority = 25

    async def activate(self, ctx: PluginContext) -> None:
        from merco.gateway.webhook import WebhookGateway

        ctx.register_gateway(WebhookGateway())
        logger.info("Gateway plugin activated (WebhookGateway registered)")
