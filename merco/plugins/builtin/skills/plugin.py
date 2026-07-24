"""Skill plugin — creates and loads SkillRegistry."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from merco.plugins.base import Plugin

if TYPE_CHECKING:
    from merco.plugins.base import PluginContext

logger = logging.getLogger("merco.plugins.skills")


class SkillPlugin(Plugin):
    """Creates SkillRegistry and injects it into the agent and skill_view tool."""

    name = "skills"
    version = "1.0.0"
    description = "Loads skills and injects the skill registry"
    priority = 60

    async def activate(self, ctx: PluginContext) -> None:
        from merco.skills.registry import SkillRegistry

        registry = SkillRegistry()
        registry.load_from_paths(ctx.config.skills_paths)

        ctx.skill_registry = registry
        if ctx.agent is not None:
            ctx.agent.skill_registry = registry

        skill_tool = ctx.tool_registry.get("skill_view")
        if skill_tool is not None and hasattr(skill_tool, "set_skill_registry"):
            skill_tool.set_skill_registry(registry)

        logger.info("Skill plugin activated (paths=%s)", ctx.config.skills_paths)
