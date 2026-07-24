"""SubAgent plugin — creates TodoManager + SubAgentManager and wires TaskTool."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from merco.plugins.base import Plugin

if TYPE_CHECKING:
    from merco.plugins.base import PluginContext

logger = logging.getLogger("merco.plugins.subagent")


class SubAgentPlugin(Plugin):
    """Creates todo manager, sub-agent manager, and wires TaskTool."""

    name = "subagent"
    version = "1.0.0"
    description = "Creates sub-agent dispatch and todo manager"
    priority = 40

    async def activate(self, ctx: PluginContext) -> None:
        from merco.agents.subagent import SubAgentManager
        from merco.todo.manager import TodoManager

        todo_manager = TodoManager(f"{ctx.config.memory_path}/../todos.db")
        sub_agent_manager = SubAgentManager(ctx.agent, ctx.agent_profiles)

        ctx.todo_manager = todo_manager
        ctx.sub_agent_manager = sub_agent_manager
        if ctx.agent is not None:
            ctx.agent.todo_manager = todo_manager
            ctx.agent.sub_agent_manager = sub_agent_manager

        task_tool = ctx.tool_registry.get("task")
        if task_tool is not None:
            if hasattr(task_tool, "_todo_manager"):
                task_tool._todo_manager = todo_manager
            if hasattr(task_tool, "_sub_agent_manager"):
                task_tool._sub_agent_manager = sub_agent_manager

        logger.info("SubAgent plugin activated")
