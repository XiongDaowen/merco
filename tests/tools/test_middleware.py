"""ToolMiddleware + Chain 单测"""
import pytest
from merco.tools.middleware import ToolContext, ToolMiddleware, ToolMiddlewareChain


class StubTool:
    name = "stub"
    description = "stub"
    parameters = {}
    toolset = "test"

    async def execute(self, **kwargs):
        return {"echo": kwargs}


def test_tool_context_default():
    """ToolContext 默认值"""
    ctx = ToolContext(tool_name="t", arguments={"a": 1})
    assert ctx.tool is None
    assert ctx.result is None
    assert ctx.error is None
    assert ctx.metadata == {}


def test_middleware_abc():
    """ToolMiddleware 不能直接实例化"""
    with pytest.raises(TypeError):
        ToolMiddleware()  # noqa


class PassMiddleware(ToolMiddleware):
    name = "pass"

    async def before(self, ctx):
        return None

    async def after(self, ctx):
        return None

    async def on_error(self, ctx):
        return None


async def test_chain_empty_executes_tool():
    """空 chain 直接调工具"""
    chain = ToolMiddlewareChain()
    ctx = ToolContext(tool_name="t", arguments={"x": 1}, tool=StubTool())
    result = await chain.execute(ctx, lambda: StubTool().execute(**ctx.arguments))
    assert result == {"echo": {"x": 1}}


class ShortCircuitMiddleware(ToolMiddleware):
    name = "short"
    async def before(self, ctx):
        return {"short_circuit": True}

    async def after(self, ctx):
        return None

    async def on_error(self, ctx):
        return None


async def test_chain_before_short_circuit():
    """before 返回 dict 短路"""
    chain = ToolMiddlewareChain()
    chain.use(ShortCircuitMiddleware())
    called = []

    async def call_tool():
        called.append(True)
        return {"ok": True}

    ctx = ToolContext(tool_name="t", arguments={})
    result = await chain.execute(ctx, call_tool)
    assert result == {"short_circuit": True}
    assert called == []


class OrderRecorder(ToolMiddleware):
    def __init__(self, name, events):
        self.name = name
        self.events = events

    async def before(self, ctx):
        self.events.append(f"{self.name}:before")

    async def after(self, ctx):
        self.events.append(f"{self.name}:after")

    async def on_error(self, ctx):
        self.events.append(f"{self.name}:on_error")


async def test_chain_order_onion():
    """洋葱模型：before 正序，after 逆序"""
    chain = ToolMiddlewareChain()
    events = []
    a = OrderRecorder("a", events)
    b = OrderRecorder("b", events)
    chain.use(a)
    chain.use(b)

    ctx = ToolContext(tool_name="t", arguments={}, tool=StubTool())
    await chain.execute(ctx, lambda: StubTool().execute())

    assert events == ["a:before", "b:before", "b:after", "a:after"]


async def test_chain_on_error_invokes_in_reverse():
    """on_error 逆序执行"""
    chain = ToolMiddlewareChain()
    events = []
    a = OrderRecorder("a", events)
    b = OrderRecorder("b", events)
    chain.use(a)
    chain.use(b)

    async def fail():
        raise RuntimeError("boom")

    ctx = ToolContext(tool_name="t", arguments={}, tool=StubTool())
    with pytest.raises(RuntimeError):
        await chain.execute(ctx, fail)

    assert events == ["a:before", "b:before", "b:on_error", "a:on_error"]


class ErrorOverrideMiddleware(ToolMiddleware):
    name = "error_override"

    async def before(self, ctx):
        return None

    async def after(self, ctx):
        return None

    async def on_error(self, ctx):
        return {"error": str(ctx.error), "recovered": True}


async def test_chain_on_error_can_short_circuit():
    """on_error 返回 dict → 短路"""
    chain = ToolMiddlewareChain()
    chain.use(ErrorOverrideMiddleware())

    async def fail():
        raise ValueError("nope")

    ctx = ToolContext(tool_name="t", arguments={}, tool=StubTool())
    result = await chain.execute(ctx, fail)
    assert result == {"error": "nope", "recovered": True}


async def test_chain_after_can_replace_result():
    """after 返回 dict → 替换 result"""
    chain = ToolMiddlewareChain()

    class ReplaceAfter(ToolMiddleware):
        name = "replace"
        async def before(self, ctx):
            return None

        async def after(self, ctx):
            return {"replaced": True}

        async def on_error(self, ctx):
            return None

    chain.use(ReplaceAfter())
    ctx = ToolContext(tool_name="t", arguments={}, tool=StubTool())
    result = await chain.execute(ctx, lambda: {"original": True})
    assert result == {"replaced": True}


async def test_chain_before_returns_context_continues():
    """before 返回 ctx → 继续"""
    chain = ToolMiddlewareChain()

    class Mutator(ToolMiddleware):
        name = "mutate"
        async def before(self, ctx):
            ctx.metadata["x"] = 1
            return ctx

        async def after(self, ctx):
            return None

        async def on_error(self, ctx):
            return None

    chain.use(Mutator())
    ctx = ToolContext(tool_name="t", arguments={}, tool=StubTool())
    await chain.execute(ctx, lambda: {})
    assert ctx.metadata["x"] == 1
