"""ToolContext + ToolMiddleware + ToolMiddlewareChain"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path

import merco.sandbox.snapshot as snapshot
from merco.sandbox.confirm import confirm_edit
from merco.sandbox.guard import GuardAction


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

    def use(self, middleware: ToolMiddleware) -> ToolMiddlewareChain:
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


class GuardMiddleware(ToolMiddleware):
    """包装 ToolGuard — DENY 返回错误，ASK 抛异常，ALLOW 继续"""

    name = "guard"

    def __init__(self, guard):
        self.guard = guard

    async def before(self, ctx: ToolContext):
        result = await self.guard.check(ctx.tool_name, ctx.arguments)
        if result.action == GuardAction.DENY:
            return {"error": f"操作被安全守卫拒绝: {result.reason}", "tool": ctx.tool_name}
        if result.action == GuardAction.ASK:
            from merco.sandbox.guard import GuardConfirmationRequired

            raise GuardConfirmationRequired(result)
        return None

    async def after(self, ctx: ToolContext):
        return None

    async def on_error(self, ctx: ToolContext):
        return None


class ErrorHandlingMiddleware(ToolMiddleware):
    """工具异常 → 结构化 tool_error 结果"""

    name = "error_handling"

    async def before(self, ctx: ToolContext):
        return None

    async def after(self, ctx: ToolContext):
        return None

    async def on_error(self, ctx: ToolContext):
        from merco.tools.errors import tool_error

        return tool_error(
            ctx.error,
            ctx.tool_name,
            getattr(ctx.tool, "parameters", None) if ctx.tool else None,
        )


class EditApplyMiddleware(ToolMiddleware):
    """应用 EditFile planned_edit：确认、快照、写入"""

    name = "edit_apply"

    def __init__(self, diff_view: str = "unified"):
        self.diff_view = diff_view

    async def before(self, ctx: ToolContext):
        return None

    async def after(self, ctx: ToolContext):
        result = ctx.result or {}
        if not isinstance(result, dict) or not result.get("planned_edit"):
            return None

        path = result["path"]
        old_content = result["old_content"]
        new_content = result["new_content"]
        diff = result["diff"]

        approved = await confirm_edit(diff, path, 1, old_content, new_content, self.diff_view)
        if not approved:
            return {
                "success": False,
                "path": path,
                "message": "用户已取消修改",
                "diff": diff,
            }

        snapshot.track(path, old_content)
        Path(path).write_text(new_content, encoding="utf-8")
        return {
            "success": True,
            "path": path,
            "diff": diff,
            "message": f"已修改 `{path}`",
        }

    async def on_error(self, ctx: ToolContext):
        return None
