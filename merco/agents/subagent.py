"""SubAgentManager — 子代理派发"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from merco.core.agent import Agent

logger = logging.getLogger("merco.agents.subagent")


class SubAgentManager:
    """子代理派发管理器"""

    def __init__(self, parent: "Agent"):
        self._parent = parent
        self._active: dict[str, "Agent"] = {}

    async def dispatch(self, todo_id: str, prompt: str, agent_name: str = "default") -> str:
        """派发子代理执行任务，返回 subagent_id"""
        # 1. 创建子 Agent
        sub_agent = self._create_sub_agent(agent_name)

        # 2. 更新 Todo 状态
        self._parent.todo_manager.update(todo_id, status="in_progress", assigned_to=sub_agent.session.id)

        # 3. 执行子代理
        try:
            result = await sub_agent.run(prompt)
            # 4. 更新 Todo 结果
            self._parent.todo_manager.update(todo_id, status="completed", result=result)
        except Exception as e:
            logger.warning("子代理执行失败: %s", e)
            self._parent.todo_manager.update(todo_id, status="failed", result=str(e))
            result = f"Error: {e}"

        # 5. 结果注入父 context
        self._inject_result_to_parent(todo_id, result)

        # 6. 触发事件
        await self._parent.hooks.emit("subagent.completed", todo_id=todo_id, result=result)

        return sub_agent.session.id

    def _create_sub_agent(self, agent_name: str) -> "Agent":
        """创建子 Agent，继承父的配置"""
        from merco.core.agent import Agent
        from merco.core.session import Session

        # 复制父的 config/tools
        sub_agent = Agent(
            config=self._parent.config,
            tool_registry=self._parent.tool_registry,
        )
        # 强制新 session（Agent.__init__ 会 resume_or_create 恢复父会话）
        sub_agent.session = Session(store=sub_agent._session_store)
        sub_agent._session_store.create_session(sub_agent.session.id)
        self._active[sub_agent.session.id] = sub_agent
        return sub_agent

    def _inject_result_to_parent(self, todo_id: str, result: str):
        """把子代理结果注入父代理的 context"""
        self._parent.context.add({
            "role": "tool",
            "content": f"[Todo {todo_id}] 子代理结果:\n{result}",
            "tool_call_id": f"todo_{todo_id}",
        })
