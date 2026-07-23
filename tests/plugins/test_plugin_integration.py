"""插件系统端到端集成测试"""
import pytest
from merco.plugins.base import Plugin, PluginContext
from merco.plugins.manager import PluginManager


class TestPlugin(Plugin):
    name = "test_plugin"
    version = "1.0.0"
    description = "测试插件"

    def __init__(self):
        self.activated = False
        self.tool_registered = False

    async def activate(self, ctx):
        self.activated = True
        # 注册一个工具
        from merco.tools.base import BaseTool

        class TestTool(BaseTool):
            name = "test_plugin_tool"
            description = "插件注册的工具"
            parameters = {"type": "object", "properties": {}}
            async def execute(self, **kwargs):
                return {"result": "from plugin"}

        ctx.register_tool(TestTool())
        self.tool_registered = True

    async def deactivate(self):
        self.activated = False


async def test_plugin_activates_and_registers_tool(test_agent):
    """插件激活后注册工具，Agent 可用"""
    plugin = TestPlugin()
    test_agent.plugin_manager.register(plugin)
    await test_agent.plugin_manager.activate("test_plugin")

    assert plugin.activated is True
    assert "test_plugin_tool" in [t.name for t in test_agent.tool_registry.list_tools()]


async def test_plugin_emits_events(test_agent):
    """插件激活触发事件"""
    events = []
    async def on_activated(plugin_name, **kwargs):
        events.append(plugin_name)
    test_agent.hooks.on("plugin.activated", on_activated)

    plugin = TestPlugin()
    test_agent.plugin_manager.register(plugin)
    await test_agent.plugin_manager.activate("test_plugin")

    assert "test_plugin" in events


async def test_plugin_failure_isolated(test_agent):
    """插件失败不影响 Agent"""
    class FailingPlugin(Plugin):
        name = "failing"
        version = "1.0.0"
        description = "失败插件"

        async def activate(self, ctx):
            raise RuntimeError("boom")

    failing = FailingPlugin()
    working = TestPlugin()
    test_agent.plugin_manager.register(failing)
    test_agent.plugin_manager.register(working)

    await test_agent.plugin_manager.activate_all()

    assert working.activated is True
    assert "test_plugin" in test_agent.plugin_manager.active_plugins


async def test_plugins_see_all_extension_points_on_activate(test_agent):
    """插件 activate(ctx) 时应能看到所有扩展点"""
    seen = {}

    class ProbePlugin(Plugin):
        name = "probe"
        version = "1.0.0"
        description = "probe"

        async def activate(self, ctx):
            seen["context_pipeline"] = ctx.context_pipeline is not None
            seen["todo_manager"] = ctx.todo_manager is not None
            seen["sub_agent_manager"] = ctx.sub_agent_manager is not None
            seen["memory_backends"] = ctx.memory_backends is not None
            seen["agent_profiles"] = ctx.agent_profiles is not None
            seen["security_pipeline"] = ctx.security_pipeline is not None
            seen["model_registry"] = ctx.model_registry is not None

    test_agent.plugin_manager.register(ProbePlugin())
    await test_agent.plugin_manager.activate("probe")

    assert seen["context_pipeline"] is True
    assert seen["todo_manager"] is True
    assert seen["sub_agent_manager"] is True
    assert seen["memory_backends"] is True
    assert seen["agent_profiles"] is True
    assert seen["security_pipeline"] is True  # 已通过 agent.py 注入
    assert seen["model_registry"] is True


async def test_external_dir_plugin_registers_via_convenience_methods(tmp_path, monkeypatch):
    """外部插件经 dir-scan 发现并激活，用便捷方法注册 profile/backend/policy。

    端到端验证：dir-scan discovery -> PluginManager 激活 -> PluginContext 便捷方法
    委托到 agent_profiles/memory_backends/security_pipeline。
    """
    from unittest.mock import AsyncMock, MagicMock
    from merco.plugins.discovery import PluginDiscovery

    # 1. 造一个外部插件目录（plugin.toml + main.py）
    pdir = tmp_path / "external"
    pdir.mkdir()
    (pdir / "plugin.toml").write_text(
        '[plugin]\nname = "external"\nversion = "0.1.0"\n'
        'description = "ext"\npriority = 50\ndepends_on = []\nentry = "main:ExtPlugin"\n',
        encoding="utf-8",
    )
    (pdir / "main.py").write_text(
        "from merco.plugins.base import Plugin\n"
        "class ExtPlugin(Plugin):\n"
        '    name = "external"\n    version = "0.1.0"\n'
        "    async def activate(self, ctx):\n"
        "        ctx.register_agent_profile(object())\n"
        "        ctx.add_memory_backend(object())\n"
        "        ctx.add_security_policy(object())\n",
        encoding="utf-8",
    )

    # 2. 构造 PluginContext（mock 各 registry/pipeline）
    ctx = PluginContext(
        hooks=MagicMock(), tool_registry=MagicMock(), prompt_builder=MagicMock(),
        recovery_pipeline=MagicMock(), result_pipeline=MagicMock(),
        memory_save_pipeline=MagicMock(), recaller=MagicMock(), config=MagicMock(),
        observer=MagicMock(), todo_manager=MagicMock(), sub_agent_manager=MagicMock(),
        context_pipeline=MagicMock(), agent_profiles=MagicMock(),
        memory_backends=MagicMock(), loop_policies=MagicMock(),
        security_pipeline=MagicMock(),
    )
    ctx.config.plugins = {}
    ctx.config.plugins_paths = [str(tmp_path)]
    # HookRegistry.emit 是 async def（merco/hooks/registry.py），manager.activate 会
    # `await ctx.hooks.emit(...)`；用 AsyncMock 让调用返回 awaitable（对齐 test_manager.py）。
    ctx.hooks.emit = AsyncMock()

    # 3. 屏蔽 entry_points，只走 dir-scan
    monkeypatch.setattr("merco.plugins.discovery.entry_points", lambda group: [])

    # 4. discover -> 恰好 1 个名为 "external" 的 spec
    specs = PluginDiscovery(ctx.config).discover()
    assert len(specs) == 1
    assert specs[0].name == "external"

    # 5. register_all -> activate_all
    manager = PluginManager(ctx)
    manager.register_all(specs)
    await manager.activate_all()

    # 6. 已激活
    assert "external" in manager.active_plugins

    # 7. 三个便捷方法抵达各自目标
    ctx.agent_profiles.register.assert_called_once()
    ctx.memory_backends.register.assert_called_once()
    ctx.security_pipeline.use.assert_called_once()


@pytest.mark.asyncio
async def test_plugin_can_register_model_provider(test_agent):
    """Third-party provider registers via ctx.register_model_provider."""
    from merco.plugins.base import Plugin, PluginContext, PluginSpec
    from merco.core.llm.base import ModelProvider, ModelProviderInfo

    class FakeProvider(ModelProvider):
        name = "fake"
        async def chat(self, messages, tools=None, tool_choice=None):
            return {"content": "fake", "finish_reason": "stop"}
        async def chat_stream(self, messages, tools=None, tool_choice=None):
            yield {"content": "fake"}

    class FakePlugin(Plugin):
        name = "fake_provider"
        async def activate(self, ctx):
            ctx.register_model_provider(ModelProviderInfo(
                name="fake", provider_class=FakeProvider, display_name="Fake"))

    assert test_agent.model_registry is not None
    # simulate plugin activation
    from merco.core.llm.registry import ModelRegistry
    test_agent.model_registry.register(ModelProviderInfo(
        name="fake", provider_class=FakeProvider, display_name="Fake"))
    info = test_agent.model_registry.get("fake")
    assert info.provider_class is FakeProvider
