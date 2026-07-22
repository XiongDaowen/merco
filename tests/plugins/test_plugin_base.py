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
    """PluginContext 不直接暴露 security_pipeline，避免插件绕过沙箱

    NOTE: 这一行为已在新版本中翻转。PluginContext 现在显式暴露
    security_pipeline 给插件用于注册安全策略（add_security_policy）。
    旧断言 `not hasattr(ctx, "security_pipeline")` 已不再适用 —— 保留
    本测试作为安全审计的形状检查：在没有显式传入 security_pipeline 时，
    属性应是 None（默认未注入路径），而非被隐藏。
    """
    assert ctx.security_pipeline is None


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


def test_plugin_priority_and_depends_on_defaults():
    """Plugin 默认 priority=50, depends_on=[]"""
    class P(Plugin):
        name = "p"
        async def activate(self, ctx): ...
    assert P.priority == 50
    assert P.depends_on == []


def test_plugin_priority_overridable():
    """Plugin 可覆盖 priority 和 depends_on"""
    class Q(Plugin):
        name = "q"
        priority = 100
        depends_on = ["p"]
        async def activate(self, ctx): ...
    assert Q.priority == 100
    assert Q.depends_on == ["p"]


def test_plugin_context_security_pipeline_exposed():
    """PluginContext 暴露 security_pipeline"""
    from unittest.mock import MagicMock
    from merco.plugins.base import PluginContext
    sec = MagicMock()
    ctx = PluginContext(
        hooks=MagicMock(), tool_registry=MagicMock(), prompt_builder=MagicMock(),
        recovery_pipeline=MagicMock(), result_pipeline=MagicMock(),
        memory_save_pipeline=MagicMock(), recaller=MagicMock(), config=MagicMock(),
        security_pipeline=sec,
    )
    assert ctx.security_pipeline is sec


def test_convenience_methods_delegate():
    """4 个便捷方法委托到底层 registry/pipeline"""
    from unittest.mock import MagicMock
    from merco.plugins.base import PluginContext
    ctx = PluginContext(
        hooks=MagicMock(), tool_registry=MagicMock(), prompt_builder=MagicMock(),
        recovery_pipeline=MagicMock(), result_pipeline=MagicMock(),
        memory_save_pipeline=MagicMock(), recaller=MagicMock(), config=MagicMock(),
        observer=MagicMock(), todo_manager=MagicMock(), sub_agent_manager=MagicMock(),
        context_pipeline=MagicMock(), agent_profiles=MagicMock(),
        memory_backends=MagicMock(), loop_policies=MagicMock(),
        security_pipeline=MagicMock(),
    )
    profile, policy, backend, sec_policy = object(), object(), object(), object()
    ctx.register_agent_profile(profile)
    ctx.register_loop_policy(policy)
    ctx.add_memory_backend(backend)
    ctx.add_security_policy(sec_policy)
    ctx.agent_profiles.register.assert_called_once_with(profile)
    ctx.loop_policies.register.assert_called_once_with(policy)
    ctx.memory_backends.register.assert_called_once_with(backend)
    ctx.security_pipeline.use.assert_called_once_with(sec_policy)


def test_add_security_policy_without_pipeline_raises():
    """security_pipeline 为 None 时 add_security_policy 抛 RuntimeError"""
    from unittest.mock import MagicMock
    from merco.plugins.base import PluginContext
    ctx = PluginContext(
        hooks=MagicMock(), tool_registry=MagicMock(), prompt_builder=MagicMock(),
        recovery_pipeline=MagicMock(), result_pipeline=MagicMock(),
        memory_save_pipeline=MagicMock(), recaller=MagicMock(), config=MagicMock(),
    )  # security_pipeline 默认 None
    try:
        ctx.add_security_policy(object())
        assert False, "应抛 RuntimeError"
    except RuntimeError:
        pass
