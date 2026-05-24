"""工具注册中心 — 管理所有可用工具，支持 toolset 过滤、可用性检查、动态描述"""

from typing import Optional
from .base import BaseTool


class ToolRegistry:
    """中央工具注册表

    支持：
    - toolset 分组：通过 set_enabled_toolsets() 控制启用哪些分组
    - check_fn 过滤：工具不可用时自动从 LLM 列表中移除
    - 动态描述：get_definitions(context) 可传入运行时上下文增强工具描述
    """

    def __init__(self):
        self._tools: dict[str, BaseTool] = {}
        self._enabled_toolsets: set | None = None  # None = 全部启用

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
        """列出所有已注册工具（不区分 toolset）"""
        return list(self._tools.values())

    def set_enabled_toolsets(self, toolsets: list[str] | None):
        """设置启用的 toolset 分组。None = 全部启用。

        工具注册后调用此方法限制可见范围。
        例如 set_enabled_toolsets(["file", "bash"]) 只暴露文件操作和终端工具。
        """
        self._enabled_toolsets = set(toolsets) if toolsets is not None else None

    def get_definitions(self, context: dict | None = None) -> list[dict]:
        """获取可用工具定义（用于 LLM function calling）

        过滤规则：
        1. check() 返回 False 的工具被排除
        2. 如果设置了 enabled_toolsets，只包含匹配分组的工具

        context 传给 tool.describe() 用于动态描述增强。
        """
        definitions = []
        for tool in self._tools.values():
            # 可用性检查
            if not tool.check():
                continue
            # toolset 过滤
            if self._enabled_toolsets is not None and tool.toolset not in self._enabled_toolsets:
                continue
            definitions.append(tool.get_definition(context))
        return definitions

    async def execute(self, tool_name: str, **kwargs) -> dict:
        """执行指定工具（异常自动转为结构化错误，喂回 LLM 自愈）"""
        tool = self.get(tool_name)
        if tool is None:
            return {"error": f"工具 '{tool_name}' 不存在"}

        try:
            return await tool.execute(**kwargs)
        except Exception as e:
            from openmercury.core.self_healing import tool_error
            return tool_error(e, tool_name, getattr(tool, 'parameters', None))


# 模块级全局单例 — 工具模块在 import 时通过此实例自注册
tool_registry = ToolRegistry()
