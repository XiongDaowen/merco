"""Plugin base class + PluginContext unit tests"""
import pytest
from merco.plugins.base import Plugin, PluginContext
from merco.tools.base import BaseTool


class FakeTool(BaseTool):
    name = "fake_tool"
    description = "test tool"
    parameters = {"type": "object", "properties": {}}

    async def execute(self, **kwargs):
        return {"result": "ok"}


class FakePlugin(Plugin):
    name = "fake"
    version = "1.0.0"
    description = "test plugin"

    def __init__(self):
        self.activated = False
        self.deactivated = False

    async def activate(self, ctx):
        self.activated = True
        ctx.register_tool(FakeTool())

    async def deactivate(self):
        self.deactivated = True


def test_plugin_abc_requires_activate():
    """Plugin base class cannot be instantiated directly"""
    with pytest.raises(TypeError):
        Plugin()  # noqa


def test_plugin_context_has_all_extension_points(ctx):
    """PluginContext exposes all extension points"""
    assert hasattr(ctx, 'hooks')
    assert hasattr(ctx, 'tool_registry')
    assert hasattr(ctx, 'prompt_builder')
    assert hasattr(ctx, 'recovery_pipeline')
    assert hasattr(ctx, 'result_pipeline')
    assert hasattr(ctx, 'memory_save_pipeline')
    assert hasattr(ctx, 'recaller')
    assert hasattr(ctx, 'config')
    assert hasattr(ctx, 'observer')


def test_plugin_context_convenience_methods(ctx):
    """PluginContext convenience methods delegate to underlying objects"""
    plugin = FakePlugin()

    # Activate to register tool via convenience method
    import asyncio
    asyncio.run(plugin.activate(ctx))

    assert plugin.activated is True
    tools = ctx.tool_registry.list_tools()
    assert any(t.name == "fake_tool" for t in tools)


def test_plugin_deactivate_default():
    """Plugin.deactivate has default empty implementation"""

    class MinimalPlugin(Plugin):
        name = "minimal"
        version = "0.1.0"
        description = "minimal plugin"

        async def activate(self, ctx):
            pass

    plugin = MinimalPlugin()
    # Should not raise - default deactivate is a no-op
    import asyncio
    asyncio.run(plugin.deactivate())


def test_plugin_context_does_not_expose_security_pipeline(ctx):
    """PluginContext 不直接暴露 security_pipeline，避免插件绕过沙箱"""
    assert not hasattr(ctx, "security_pipeline")


def test_add_processor_rejects_non_whitelisted_pipeline(ctx):
    """add_processor 只允许白名单 pipeline"""
    with pytest.raises(ValueError, match="not extensible"):
        ctx.add_processor("security_pipeline", object())


def test_add_processor_allows_context_pipeline(ctx):
    """add_processor 允许白名单内 pipeline"""
    class DummyProcessor:
        name = "dummy"
        async def process(self, messages, **kwargs):
            return messages

    ctx.add_processor("context_pipeline", DummyProcessor())
    assert any(p.name == "dummy" for p in ctx.context_pipeline._processors)


@pytest.fixture
def ctx(tmp_path):
    """Construct PluginContext"""
    from merco.hooks.registry import HookRegistry
    from merco.tools.registry import ToolRegistry
    from merco.core.agent import PromptBuilder
    from merco.memory.store import MemoryStore
    from merco.memory.save_pipeline import MemorySavePipeline
    from merco.memory.recall import HybridRecaller
    from merco.core.config import MercoConfig
    from merco.context.pipeline import ContextPipeline
    from unittest.mock import MagicMock

    hooks = HookRegistry()
    tool_registry = ToolRegistry()
    prompt_builder = PromptBuilder()
    memory_store = MemoryStore(str(tmp_path / "memory"))
    config = MercoConfig()
    config.memory_path = str(tmp_path / "memory")

    return PluginContext(
        hooks=hooks,
        tool_registry=tool_registry,
        prompt_builder=prompt_builder,
        recovery_pipeline=MagicMock(),
        result_pipeline=MagicMock(),
        memory_save_pipeline=MemorySavePipeline(memory_store, hooks),
        recaller=HybridRecaller(),
        config=config,
        observer=MagicMock(),
        context_pipeline=ContextPipeline(),
    )
