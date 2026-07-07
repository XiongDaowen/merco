"""插件系统集成测试 — 覆盖插件完整生命周期与多插件协同。"""
import pytest
from merco.plugins.base import Plugin, PluginContext
from tests.integration.core.programmable_mock import Response


class TestPluginLifecycle:
    @pytest.mark.asyncio
    async def test_register_activate_deactivate_full_lifecycle(self, scenario):
        activated = {"n": 0}
        deactivated = {"n": 0}

        class LifecyclePlugin(Plugin):
            name = "lifecycle_test"
            version = "1.0.0"

            async def activate(self, ctx: PluginContext):
                activated["n"] += 1

            async def deactivate(self):
                deactivated["n"] += 1

        scenario.agent.plugin_manager.register(LifecyclePlugin())

        await scenario.agent.plugin_manager.activate("lifecycle_test")
        assert activated["n"] == 1
        assert "lifecycle_test" in scenario.agent.plugin_manager.active_plugins

        await scenario.agent.plugin_manager.deactivate("lifecycle_test")
        assert deactivated["n"] == 1
        assert "lifecycle_test" not in scenario.agent.plugin_manager.active_plugins

        await scenario.agent.plugin_manager.activate("lifecycle_test")
        assert activated["n"] == 1

    @pytest.mark.asyncio
    async def test_all_builtin_plugins_activate(self, scenario):
        active = scenario.agent.plugin_manager.active_plugins
        expected = {"observability", "skills", "mcp", "subagent", "web", "scheduler"}
        assert expected.issubset(set(active)), \
            f"missing {expected - set(active)}"


class TestPluginFailureIsolation:
    @pytest.mark.asyncio
    async def test_plugin_activation_failure_does_not_block_others(self, scenario):
        class FailingPlugin(Plugin):
            name = "failing_plugin"
            version = "1.0.0"

            async def activate(self, ctx):
                raise RuntimeError("activation failed")

        class WorkingPlugin(Plugin):
            name = "working_plugin"
            version = "1.0.0"

            async def activate(self, ctx):
                self.__class__._activated = True

        scenario.agent.plugin_manager.register(FailingPlugin())
        scenario.agent.plugin_manager.register(WorkingPlugin())

        await scenario.agent.plugin_manager.activate("failing_plugin")
        assert "failing_plugin" not in scenario.agent.plugin_manager.active_plugins

        await scenario.agent.plugin_manager.activate("working_plugin")
        assert "working_plugin" in scenario.agent.plugin_manager.active_plugins


class TestPluginHookEvents:
    @pytest.mark.asyncio
    async def test_activate_emits_plugin_activated_event(self, scenario):
        emitted = []
        scenario.agent.hooks.on("plugin.activated", lambda **kw: emitted.append(kw))

        class TestPlugin(Plugin):
            name = "event_test"
            version = "2.5.0"

            async def activate(self, ctx):
                pass

        scenario.agent.plugin_manager.register(TestPlugin())
        await scenario.agent.plugin_manager.activate("event_test")

        assert any(
            e.get("plugin_name") == "event_test" and e.get("version") == "2.5.0"
            for e in emitted
        )


class TestPluginContextShared:
    @pytest.mark.asyncio
    async def test_plugins_share_context(self, scenario):
        class PluginA(Plugin):
            name = "plugin_a"
            version = "1.0.0"

            async def activate(self, ctx: PluginContext):
                ctx.metadata["shared_value"] = "from_a"

        class PluginB(Plugin):
            name = "plugin_b"
            version = "1.0.0"
            read_value = None

            async def activate(self, ctx: PluginContext):
                self.read_value = ctx.metadata.get("shared_value")

        a = PluginA()
        b = PluginB()
        scenario.agent.plugin_manager.register(a)
        scenario.agent.plugin_manager.register(b)

        await scenario.agent.plugin_manager.activate("plugin_a")
        await scenario.agent.plugin_manager.activate("plugin_b")

        assert b.read_value == "from_a"


class TestPluginConfigGating:
    @pytest.mark.asyncio
    async def test_unknown_plugin_in_config_ignored(self, scenario):
        scenario.agent.config.plugins = scenario.agent.config.plugins or {}
        scenario.agent.config.plugins["nonexistent_plugin"] = {"enabled": True}

        await scenario.agent.plugin_manager.activate("nonexistent_plugin")
        assert "nonexistent_plugin" not in scenario.agent.plugin_manager.active_plugins
