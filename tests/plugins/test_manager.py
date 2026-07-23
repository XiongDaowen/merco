"""插件管理器单元测试"""
from unittest.mock import AsyncMock, MagicMock
import pytest
from merco.plugins.manager import PluginManager


class TestPluginManager:
    """PluginManager 测试"""

    @pytest.fixture
    def mock_context(self):
        """模拟插件上下文"""
        ctx = MagicMock()
        ctx.hooks.emit = AsyncMock()
        ctx.config = MagicMock()
        ctx.config.plugins = {}
        return ctx

    @pytest.fixture
    def manager(self, mock_context):
        """创建插件管理器实例"""
        return PluginManager(mock_context)

    @pytest.fixture
    def mock_plugin(self):
        """模拟插件实例"""
        plugin = MagicMock()
        plugin.name = "test-plugin"
        plugin.version = "1.0.0"
        plugin.activate = AsyncMock()
        plugin.deactivate = AsyncMock()
        return plugin

    def test_register_plugin(self, manager, mock_plugin):
        """测试注册插件"""
        manager.register(mock_plugin)
        assert mock_plugin.name in manager._plugins
        assert manager._plugins[mock_plugin.name] == mock_plugin

    @pytest.mark.asyncio
    async def test_activate_plugin_success(self, manager, mock_plugin, mock_context):
        """测试成功激活插件"""
        manager.register(mock_plugin)

        await manager.activate(mock_plugin.name)

        # 插件激活方法被调用
        mock_plugin.activate.assert_called_once_with(mock_context)
        # 插件被标记为激活
        assert mock_plugin.name in manager._active
        # 事件被触发
        mock_context.hooks.emit.assert_called_once_with(
            "plugin.activated",
            plugin_name=mock_plugin.name,
            version=mock_plugin.version
        )

    @pytest.mark.asyncio
    async def test_activate_already_active_plugin(self, manager, mock_plugin):
        """测试激活已经激活的插件"""
        manager.register(mock_plugin)
        manager._active.add(mock_plugin.name)

        await manager.activate(mock_plugin.name)

        # 激活方法不会被重复调用
        mock_plugin.activate.assert_not_called()

    @pytest.mark.asyncio
    async def test_activate_nonexistent_plugin(self, manager, caplog):
        """测试激活不存在的插件"""
        await manager.activate("nonexistent-plugin")

        # 应该有警告日志
        assert any("not registered" in record.message for record in caplog.records)

    @pytest.mark.asyncio
    async def test_activate_plugin_failure(self, manager, mock_plugin, mock_context, caplog):
        """测试插件激活失败"""
        manager.register(mock_plugin)
        mock_plugin.activate.side_effect = Exception("Activation failed")

        await manager.activate(mock_plugin.name)

        # 插件不会被标记为激活
        assert mock_plugin.name not in manager._active
        # 错误日志被记录
        assert any("activation failed" in record.message for record in caplog.records)
        # 错误事件被触发
        mock_context.hooks.emit.assert_any_call(
            "plugin.error",
            plugin_name=mock_plugin.name,
            error="Activation failed"
        )

    @pytest.mark.asyncio
    async def test_activate_plugin_event_emit_failure(self, manager, mock_plugin, mock_context, caplog):
        """测试激活事件触发失败不影响主流程"""
        manager.register(mock_plugin)
        # 第一次调用(activated)抛出异常，第二次调用(error)成功
        mock_context.hooks.emit.side_effect = [Exception("Emit failed"), None]

        await manager.activate(mock_plugin.name)

        # 插件仍然被标记为激活
        assert mock_plugin.name in manager._active
        # 异常不会被抛出，错误会被捕获
        assert any("activation failed" in record.message for record in caplog.records)

    @pytest.mark.asyncio
    async def test_deactivate_plugin_success(self, manager, mock_plugin, mock_context):
        """测试成功停用插件"""
        manager.register(mock_plugin)
        manager._active.add(mock_plugin.name)

        await manager.deactivate(mock_plugin.name)

        # 停用方法被调用
        mock_plugin.deactivate.assert_called_once()
        # 插件被移出激活集合
        assert mock_plugin.name not in manager._active
        # 事件被触发
        mock_context.hooks.emit.assert_called_once_with(
            "plugin.deactivated",
            plugin_name=mock_plugin.name
        )

    @pytest.mark.asyncio
    async def test_deactivate_nonexistent_plugin(self, manager):
        """测试停用不存在的插件"""
        # 不应该抛出异常
        await manager.deactivate("nonexistent-plugin")

    @pytest.mark.asyncio
    async def test_deactivate_not_active_plugin(self, manager, mock_plugin):
        """测试停用未激活的插件"""
        manager.register(mock_plugin)

        await manager.deactivate(mock_plugin.name)

        # 停用方法仍然会被调用（即使未激活）
        mock_plugin.deactivate.assert_called_once()

    @pytest.mark.asyncio
    async def test_deactivate_plugin_failure(self, manager, mock_plugin, caplog):
        """测试插件停用失败"""
        manager.register(mock_plugin)
        manager._active.add(mock_plugin.name)
        mock_plugin.deactivate.side_effect = Exception("Deactivation failed")

        await manager.deactivate(mock_plugin.name)

        # 插件仍然被移出激活集合
        assert mock_plugin.name not in manager._active
        # 错误日志被记录
        assert any("deactivation failed" in record.message for record in caplog.records)

    @pytest.mark.asyncio
    async def test_deactivate_plugin_event_emit_failure(self, manager, mock_plugin, mock_context):
        """测试停用事件触发失败不影响主流程"""
        manager.register(mock_plugin)
        manager._active.add(mock_plugin.name)
        mock_context.hooks.emit.side_effect = Exception("Emit failed")

        # 不应该抛出异常
        await manager.deactivate(mock_plugin.name)

        # 插件仍然被移出激活集合
        assert mock_plugin.name not in manager._active

    @pytest.mark.asyncio
    async def test_activate_all_plugins(self, manager, mock_context):
        """测试激活所有插件"""
        # 创建多个插件
        plugin1 = MagicMock()
        plugin1.name = "plugin1"
        plugin1.version = "1.0.0"
        plugin1.activate = AsyncMock()

        plugin2 = MagicMock()
        plugin2.name = "plugin2"
        plugin2.version = "2.0.0"
        plugin2.activate = AsyncMock()

        # 默认禁用plugin2
        mock_context.config.plugins = {
            "plugin2": {"enabled": False}
        }

        manager.register(plugin1)
        manager.register(plugin2)

        await manager.activate_all()

        # plugin1应该被激活（默认启用）
        assert "plugin1" in manager._active
        plugin1.activate.assert_called_once()

        # plugin2应该不被激活（显式禁用）
        assert "plugin2" not in manager._active
        plugin2.activate.assert_not_called()

    @pytest.mark.asyncio
    async def test_deactivate_all_plugins(self, manager):
        """测试停用所有插件"""
        plugin1 = MagicMock()
        plugin1.name = "plugin1"
        plugin1.deactivate = AsyncMock()

        plugin2 = MagicMock()
        plugin2.name = "plugin2"
        plugin2.deactivate = AsyncMock()

        manager.register(plugin1)
        manager.register(plugin2)
        manager._active.add("plugin1")
        manager._active.add("plugin2")

        await manager.deactivate_all()

        # 所有插件都被停用
        plugin1.deactivate.assert_called_once()
        plugin2.deactivate.assert_called_once()
        assert len(manager._active) == 0

    def test_active_plugins_property(self, manager, mock_plugin):
        """测试active_plugins属性"""
        manager.register(mock_plugin)
        manager._active.add(mock_plugin.name)

        assert manager.active_plugins == [mock_plugin.name]
        assert isinstance(manager.active_plugins, list)

    def test_register_all_specs(self, manager):
        """register_all 存 specs"""
        from merco.plugins.base import PluginSpec
        spec = PluginSpec(name="from-spec", source="entrypoint", loader=lambda: MagicMock)
        manager.register_all([spec])
        assert "from-spec" in manager._specs
        assert manager._specs["from-spec"] is spec

    def test_meta_from_spec(self, manager):
        """_meta 返回 spec 的 priority/depends_on"""
        from merco.plugins.base import PluginSpec
        spec = PluginSpec(name="m", source="dir", priority=80, depends_on=["x"], loader=lambda: MagicMock)
        manager.register_all([spec])
        assert manager._meta("m") == (80, ["x"])

    def test_meta_defaults_for_manual_plugin(self, manager, mock_plugin):
        """手动注册（无 spec）的 _meta 返回默认 (50, [])"""
        manager.register(mock_plugin)
        assert manager._meta(mock_plugin.name) == (50, [])

    def test_all_names_union(self, manager, mock_plugin):
        """_all_names 是 _plugins 与 _specs 的并集"""
        from merco.plugins.base import PluginSpec
        manager.register(mock_plugin)
        manager.register_all([PluginSpec(name="spec-only", source="dir", loader=lambda: MagicMock)])
        names = set(manager._all_names())
        assert names == {mock_plugin.name, "spec-only"}

    def test_resolve_order_priority_then_name(self, manager):
        """同无依赖，按 priority 降序、name 升序"""
        from merco.plugins.base import PluginSpec
        manager.register_all([
            PluginSpec(name="low", source="dir", priority=10, loader=lambda: MagicMock),
            PluginSpec(name="high", source="dir", priority=90, loader=lambda: MagicMock),
            PluginSpec(name="mid", source="dir", priority=50, loader=lambda: MagicMock),
        ])
        order = manager._resolve_order(manager._all_names())
        assert order == ["high", "mid", "low"]

    def test_resolve_order_topological(self, manager):
        """depends_on 决定拓扑序：b 依赖 a，a 先"""
        from merco.plugins.base import PluginSpec
        manager.register_all([
            PluginSpec(name="b", source="dir", priority=99, depends_on=["a"], loader=lambda: MagicMock),
            PluginSpec(name="a", source="dir", priority=1, loader=lambda: MagicMock),
        ])
        order = manager._resolve_order(manager._all_names())
        assert order.index("a") < order.index("b")  # a 在 b 前（尽管 b priority 更高）

    def test_resolve_order_boot_only(self, manager):
        """boot_only=True 只返回 priority>=100"""
        from merco.plugins.base import PluginSpec
        manager.register_all([
            PluginSpec(name="boot", source="dir", priority=100, loader=lambda: MagicMock),
            PluginSpec(name="normal", source="dir", priority=50, loader=lambda: MagicMock),
        ])
        assert manager._resolve_order(manager._all_names(), boot_only=True) == ["boot"]

    def test_resolve_order_cycle_excluded(self, manager, caplog):
        """循环依赖节点被排除"""
        from merco.plugins.base import PluginSpec
        manager.register_all([
            PluginSpec(name="x", source="dir", depends_on=["y"], loader=lambda: MagicMock),
            PluginSpec(name="y", source="dir", depends_on=["x"], loader=lambda: MagicMock),
            PluginSpec(name="z", source="dir", loader=lambda: MagicMock),
        ])
        with caplog.at_level("WARNING"):
            order = manager._resolve_order(manager._all_names())
        assert "z" in order
        assert "x" not in order and "y" not in order

    def test_resolve_order_missing_dep_pruned(self, manager, caplog):
        """depends_on 引用不在池内的名字 -> 该节点剪枝"""
        from merco.plugins.base import PluginSpec
        manager.register_all([
            PluginSpec(name="needs_ghost", source="dir", depends_on=["ghost"], loader=lambda: MagicMock),
            PluginSpec(name="ok", source="dir", loader=lambda: MagicMock),
        ])
        with caplog.at_level("WARNING"):
            order = manager._resolve_order(manager._all_names())
        assert "ok" in order
        assert "needs_ghost" not in order

    @pytest.mark.asyncio
    async def test_activate_from_spec_lazy(self, mock_context):
        """register_all 后 activate 能从 spec 懒实例化并激活"""
        from merco.plugins.base import PluginSpec, Plugin

        class P(Plugin):
            name = "lazy"
            version = "1.0.0"
            activated = False
            async def activate(self, ctx):
                type(P).activated = True

        manager = PluginManager(mock_context)
        manager.register_all([PluginSpec(name="lazy", source="entrypoint", loader=lambda: P)])
        await manager.activate("lazy")
        assert "lazy" in manager._active
        assert manager._plugins["lazy"].__class__ is P

    @pytest.mark.asyncio
    async def test_dep_active_check_skips(self, mock_context, caplog):
        """dep 未激活时跳过依赖它的插件"""
        from merco.plugins.base import PluginSpec, Plugin

        class Dep(Plugin):
            name = "dep"
            async def activate(self, ctx): ...

        class Need(Plugin):
            name = "need"
            async def activate(self, ctx): ...

        manager = PluginManager(mock_context)
        manager.register_all([
            PluginSpec(name="dep", source="dir", loader=lambda: Dep),
            PluginSpec(name="need", source="dir", depends_on=["dep"], loader=lambda: Need),
        ])
        # 不激活 dep，直接激活 need -> 应被跳过
        with caplog.at_level("WARNING"):
            await manager.activate("need")
        assert "need" not in manager._active

    @pytest.mark.asyncio
    async def test_activate_boot_only_high_priority(self, mock_context):
        """activate_boot 只激活 priority>=100"""
        from merco.plugins.base import PluginSpec, Plugin

        class Boot(Plugin):
            name = "boot"
            priority = 100
            async def activate(self, ctx): ...

        class Normal(Plugin):
            name = "normal"
            priority = 50
            async def activate(self, ctx): ...

        manager = PluginManager(mock_context)
        manager.register_all([
            PluginSpec(name="boot", source="dir", priority=100, loader=lambda: Boot),
            PluginSpec(name="normal", source="dir", priority=50, loader=lambda: Normal),
        ])
        await manager.activate_boot()
        assert "boot" in manager._active
        assert "normal" not in manager._active

    @pytest.mark.asyncio
    async def test_activate_all_idempotent_for_boot(self, mock_context):
        """activate_all 对已激活的 boot 插件幂等"""
        from merco.plugins.base import PluginSpec, Plugin

        calls = {"n": 0}

        class Boot(Plugin):
            name = "boot"
            priority = 100
            async def activate(self, ctx):
                calls["n"] += 1

        manager = PluginManager(mock_context)
        manager.register_all([PluginSpec(name="boot", source="dir", priority=100, loader=lambda: Boot)])
        await manager.activate_boot()
        await manager.activate_all()
        assert calls["n"] == 1  # boot.activate 只调一次

    @pytest.mark.asyncio
    async def test_activate_boot_respects_config_disabled(self, mock_context):
        """activate_boot 遵守 config.plugins.<boot>.enabled=False：禁用的 boot 插件不激活。"""
        from merco.plugins.base import PluginSpec, Plugin

        class Boot(Plugin):
            name = "boot"
            priority = 100
            async def activate(self, ctx): ...

        mock_context.config.plugins = {"boot": {"enabled": False}}
        manager = PluginManager(mock_context)
        manager.register_all([PluginSpec(name="boot", source="dir", priority=100, loader=lambda: Boot)])

        await manager.activate_boot()

        # 禁用的 boot 插件既不在 _active 也不在 active_plugins
        assert "boot" not in manager._active
        assert "boot" not in manager.active_plugins

    @pytest.mark.asyncio
    async def test_activate_boot_failure_degrades_gracefully(self, mock_context):
        """boot 插件 activate 抛异常：捕获 + emit plugin.error，兄弟 boot 插件仍激活。"""
        from merco.plugins.base import PluginSpec, Plugin

        class BadBoot(Plugin):
            name = "bad-boot"
            priority = 100
            async def activate(self, ctx):
                raise RuntimeError("boot boom")

        class GoodBoot(Plugin):
            name = "good-boot"
            priority = 100
            async def activate(self, ctx): ...

        manager = PluginManager(mock_context)
        manager.register_all([
            PluginSpec(name="bad-boot", source="dir", priority=100, loader=lambda: BadBoot),
            PluginSpec(name="good-boot", source="dir", priority=100, loader=lambda: GoodBoot),
        ])

        await manager.activate_boot()

        # 失败的 boot 插件未进 _active
        assert "bad-boot" not in manager._active
        # 兄弟 boot 插件仍激活（bad-boot 名次在前，先失败；good-boot 不受影响）
        assert "good-boot" in manager._active
        # 错误事件已 emit
        mock_context.hooks.emit.assert_any_call(
            "plugin.error",
            plugin_name="bad-boot",
            error="boot boom",
        )
