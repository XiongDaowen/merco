"""工具基类"""

from abc import ABC, abstractmethod
from typing import Any


class BaseTool(ABC):
    """所有工具的基类"""

    name: str = ""
    description: str = ""
    parameters: dict = {}

    @property
    def definition(self) -> dict:
        """工具定义（用于 LLM function calling）"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    @abstractmethod
    async def execute(self, **kwargs) -> Any:
        """执行工具"""
        pass

    def validate(self, **kwargs) -> bool:
        """验证参数"""
        required = self.parameters.get("required", [])
        return all(key in kwargs for key in required)
