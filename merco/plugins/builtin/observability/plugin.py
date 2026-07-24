"""Observability plugin — creates the Agent observer via plugin activation."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from merco.plugins.base import Plugin

if TYPE_CHECKING:
    from merco.plugins.base import PluginContext

logger = logging.getLogger("merco.plugins.observability")


class ObservabilityPlugin(Plugin):
    """Creates Observer and attaches it to PluginContext."""

    name = "observability"
    version = "1.0.0"
    description = "Creates the observability observer"
    priority = 100

    async def activate(self, ctx: PluginContext) -> None:
        from merco.observability.observer import Observer

        ctx.observer = Observer(ctx.hooks)
        logger.info("Observability plugin activated")
