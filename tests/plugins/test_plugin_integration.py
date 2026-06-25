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
