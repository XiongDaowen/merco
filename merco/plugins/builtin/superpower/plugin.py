"""Superpower plugin — example builtin plugin for merco"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from merco.plugins.base import Plugin

if TYPE_CHECKING:
    from merco.plugins.base import PluginContext

logger = logging.getLogger("merco.plugins.superpower")


class SuperpowerHintChunk:
    """Prompt chunk that informs the LLM about available superpowers"""
    name = "superpower_hint"

    def enabled(self, agent) -> bool:
        return True

    def build(self, agent) -> str:
        return """## Superpowers Available
You have access to superpowers: TDD, debugging, subagent, code review.
Use them when appropriate to help the user."""


class SuperpowerPlugin(Plugin):
    """Example builtin plugin demonstrating merco's plugin system"""
    name = "superpower"
    version = "1.0.0"
    description = "Extends merco with superpower capabilities"
    priority = 10

    async def activate(self, ctx: "PluginContext") -> None:
        # 1. Register prompt chunk
        ctx.add_prompt_chunk(SuperpowerHintChunk())

        # 2. Subscribe to events
        ctx.hooks.on("agent.start", self._on_start)
        ctx.hooks.on("tool.error", self._on_tool_error)

        logger.info("Superpower plugin activated")

    async def deactivate(self) -> None:
        logger.info("Superpower plugin deactivated")

    async def _on_start(self, session_id: str = "", **kwargs):
        logger.debug("Superpower: agent.start session=%s", session_id)

    async def _on_tool_error(self, tool_name: str = "", error: str = "", **kwargs):
        logger.debug("Superpower: tool.error %s: %s", tool_name, error)
