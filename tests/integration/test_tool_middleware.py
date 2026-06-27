"""ToolMiddleware 集成测试"""
import pytest
from merco.tools.middleware import ToolMiddleware, ToolContext
from merco.tools.registry import ToolRegistry
from merco.tools.base import BaseTool


class RecordArgsTool(BaseTool):
    name = "record"
    description = "rec"
    parameters = {"type": "object", "properties": {}}
    toolset = "test"

    def __init__(self):
        self.calls = []

    async def execute(self, **kwargs):
        self.calls.append(kwargs)
        return {"ok": True}


@pytest.mark.asyncio
async def test_registry_runs_tool_with_no_middleware():
    """无中间件时直接执行"""
    reg = ToolRegistry()
    tool = RecordArgsTool()
    reg.register(tool)
    result = await reg.execute("record", x=1)
    assert result == {"ok": True}
    assert tool.calls == [{"x": 1}]


@pytest.mark.asyncio
async def test_registry_plugin_can_inject_middleware():
    """插件可在 registry 挂中间件"""
    reg = ToolRegistry()
    tool = RecordArgsTool()
    reg.register(tool)

    seen = []

    class Trace(ToolMiddleware):
        name = "trace"
        async def before(self, ctx):
            seen.append(("before", ctx.tool_name))
        async def after(self, ctx):
            seen.append(("after", ctx.tool_name))
        async def on_error(self, ctx):
            seen.append(("error", ctx.tool_name))

    reg.use(Trace())
    await reg.execute("record", x=1)
    assert seen == [("before", "record"), ("after", "record")]


@pytest.mark.asyncio
async def test_registry_plugin_can_short_circuit():
    """插件可短路工具执行"""
    reg = ToolRegistry()
    tool = RecordArgsTool()
    reg.register(tool)

    class Deny(ToolMiddleware):
        name = "deny"
        async def before(self, ctx):
            return {"error": "blocked by plugin"}
        async def after(self, ctx):
            return None
        async def on_error(self, ctx):
            return None

    reg.use(Deny())
    result = await reg.execute("record", x=1)
    assert result == {"error": "blocked by plugin"}
    assert tool.calls == []  # tool not called