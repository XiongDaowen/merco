"""Scheduler plugin — creates CronScheduler."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from merco.plugins.base import Plugin

if TYPE_CHECKING:
    from merco.plugins.base import PluginContext

logger = logging.getLogger("merco.plugins.scheduler")


class SchedulerPlugin(Plugin):
    """Creates CronScheduler and attaches it to PluginContext."""

    name = "scheduler"
    version = "1.0.0"
    description = "Creates the cron scheduler"
    priority = 20

    async def activate(self, ctx: "PluginContext") -> None:
        from merco.scheduler.cron import CronScheduler

        ctx.scheduler = CronScheduler()
        logger.info("Scheduler plugin activated")
