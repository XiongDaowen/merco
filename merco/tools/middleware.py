"""ToolContext + ToolMiddleware + ToolMiddlewareChain"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ToolContext:
    """工具执行上下文，贯穿 before/during/after"""
    tool_name: str
    arguments: dict
    tool: object | None = None
    result: dict | None = None
    error: BaseException | None = None
    metadata: dict = field(default_factory=dict)


class ToolMiddleware(ABC):
    """工具中间件基类"""
    name: str = ""

    @abstractmethod
    async def before(self, ctx: ToolContext):
        """执行前。返回 dict 短路；返回 ctx/None 继续"""
        ...

    @abstractmethod
    async def after(self, ctx: ToolContext):
        """执行后。可修改 ctx.result；返回 dict 替换 result"""
        ...

    @abstractmethod
    async def on_error(self, ctx: ToolContext):
        """异常处理。返回 dict → 错误结果；None → 抛"""
        ...


class ToolMiddlewareChain:
    """洋葱模型：before 正序，after/on_error 逆序"""

    def __init__(self):
        self._middlewares: list[ToolMiddleware] = []

    def use(self, middleware: ToolMiddleware) -> "ToolMiddlewareChain":
        self._middlewares.append(middleware)
        return self

    async def execute(self, ctx: ToolContext, call_tool) -> dict:
        for mw in self._middlewares:
            r = await mw.before(ctx)
            if isinstance(r, dict):
                return r
            if isinstance(r, ToolContext):
                ctx = r

        try:
            result = call_tool()
            if hasattr(result, "__await__"):
                result = await result
            ctx.result = result
        except BaseException as e:
            ctx.error = e
            for mw in reversed(self._middlewares):
                r = await mw.on_error(ctx)
                if isinstance(r, dict):
                    return r
            raise

        for mw in reversed(self._middlewares):
            r = await mw.after(ctx)
            if isinstance(r, dict):
                ctx.result = r
            elif isinstance(r, ToolContext):
                ctx = r
        return ctx.result
