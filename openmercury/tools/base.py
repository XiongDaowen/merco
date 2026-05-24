"""工具基类 — 所有工具继承此类，支持自注册、可用性检查、动态描述"""

from abc import ABC, abstractmethod
from typing import Any


class BaseTool(ABC):
    """所有工具的基类

    子类设置类属性即可完成注册：
    - name / description / parameters — 工具的基本定义
    - toolset — 工具所属分组（默认 "general"），用于配置驱动的启用/禁用
    - check() — 运行时可用性检查（默认 True），不可用时自动从 LLM 工具列表中隐藏
    - describe(context) — 动态描述扩展点，可在运行时根据上下文（如已加载的 skill 列表）增强工具描述
    """

    name: str = ""
    description: str = ""
    parameters: dict = {}
    toolset: str = "general"

    def check(self) -> bool:
        """运行时可用性检查。返回 False 时工具从 LLM 工具列表中隐藏。

        子类可重写以检查依赖条件（API key 已配置、依赖包已安装等）。
        """
        return True

    def describe(self, context: dict | None = None) -> str:
        """动态描述扩展点。返回工具的描述文本。

        子类可重写以根据运行时上下文增强描述。
        例如：skill_view 工具可在描述中列出当前可用的 skill 列表。
        context 由注册中心传入，包含 {skills, config, ...} 等运行时信息。
        """
        return self.description

    def get_definition(self, context: dict | None = None) -> dict:
        """构建工具定义（用于 LLM function calling），使用动态描述"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.describe(context),
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
