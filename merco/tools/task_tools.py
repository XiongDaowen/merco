"""任务委派工具 - 子代理调度"""

from .base import BaseTool


class TaskTool(BaseTool):
    """委派任务给子代理"""

    name = "task"
    description = "创建任务并派发给子代理执行"
    toolset = "task"
    parameters = {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "任务标题"},
            "description": {"type": "string", "description": "详细描述"},
            "priority": {"type": "integer", "description": "优先级 0=低 1=中 2=高", "default": 1},
            "agent": {"type": "string", "description": "指定子代理名称", "default": "default"},
        },
        "required": ["title"],
    }

    def check(self) -> bool:
        """激活！"""
        return True

    async def execute(self, title: str, description: str = "", priority: int = 1, agent: str = "default") -> dict:
        # 1. 创建 Todo
        todo = self._todo_manager.create(title, description, priority)

        # 2. 派发子代理
        subagent_id = await self._sub_agent_manager.dispatch(todo.id, description, agent)

        return {
            "todo_id": todo.id,
            "subagent_id": subagent_id,
            "status": "dispatched",
        }


from .registry import tool_registry  # noqa: E402 — 模块末尾自注册
tool_registry.register(TaskTool())
