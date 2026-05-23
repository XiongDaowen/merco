"""工具注册中心 - 管理所有可用工具"""

from typing import Optional
from .base import BaseTool


class ToolRegistry:
    """中央工具注册表"""

    def __init__(self):
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool):
        """注册一个工具"""
        self._tools[tool.name] = tool

    def unregister(self, name: str):
        """注销一个工具"""
        self._tools.pop(name, None)

    def get(self, name: str) -> Optional[BaseTool]:
        """获取工具"""
        return self._tools.get(name)

    def list_tools(self) -> list[BaseTool]:
        """列出所有已注册工具"""
        return list(self._tools.values())

    def get_definitions(self) -> list[dict]:
        """获取所有工具的定义（用于 LLM function calling）"""
        return [tool.definition for tool in self._tools.values()]

    async def execute(self, name: str, **kwargs) -> dict:
        """执行指定工具（异常自动转为结构化错误，喂回 LLM 自愈）"""
        tool = self.get(name)
        if tool is None:
            return {"error": f"工具 '{name}' 不存在"}

        try:
            return await tool.execute(**kwargs)
        except TypeError as e:
            params = list(tool.parameters.get("properties", {}).keys())
            return {
                "error": f"参数不匹配: {e}",
                "available_params": params,
                "received_params": list(kwargs.keys()),
            }
        except Exception as e:
            return {"error": f"工具执行失败: {type(e).__name__}: {e}"}
