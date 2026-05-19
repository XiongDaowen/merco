"""工具执行钩子"""

from .registry import HookRegistry


def register_tool_hooks(registry: HookRegistry):
    """注册工具相关钩子"""

    @registry.on("tool.before_execute")
    async def on_tool_before(tool_name: str, args: dict, **kwargs):
        """工具执行前"""
        pass

    @registry.on("tool.after_execute")
    async def on_tool_after(tool_name: str, result: dict, **kwargs):
        """工具执行后"""
        pass

    @registry.on("tool.error")
    async def on_tool_error(tool_name: str, error: Exception, **kwargs):
        """工具执行出错"""
        pass
