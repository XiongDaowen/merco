"""任务委派工具 - 子代理调度"""

from .base import BaseTool


class TaskTool(BaseTool):
    """委派任务给子代理"""

    name = "task"
    description = "将任务委派给子代理执行"
    toolset = "task"
    parameters = {
        "type": "object",
        "properties": {
            "description": {"type": "string", "description": "任务描述"},
            "prompt": {"type": "string", "description": "详细指令"},
            "agent": {"type": "string", "description": "指定子代理名称"},
        },
        "required": ["description", "prompt"],
    }

    def check(self) -> bool:
        """子代理调度未实现时隐藏此工具"""
        return False  # TODO: 实现后改为 True

    async def execute(self, description: str, prompt: str, agent: str = None) -> dict:
        # TODO: 实现子代理调度逻辑
        return {
            "status": "pending",
            "description": description,
            "agent": agent or "default",
            "note": "Subagent dispatch not yet implemented",
        }


from .registry import tool_registry  # noqa: E402 — 模块末尾自注册
tool_registry.register(TaskTool())
