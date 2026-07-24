"""PluginDiscovery 单元测试"""
from unittest.mock import MagicMock
from merco.plugins.discovery import PluginDiscovery
from merco.plugins.base import Plugin


class _EPPlugin(Plugin):
    name = "ep_test"
    version = "1.0.0"
    priority = 60
    depends_on = []
    async def activate(self, ctx): ...


def _fake_ep(name, cls):
    ep = MagicMock()
    ep.name = name
    ep.load = lambda: cls
    return ep


def _config_with(plugins=None, paths=None):
    cfg = MagicMock()
    cfg.plugins = plugins or {}
    cfg.plugins_paths = paths or []
    return cfg


def test_discover_entrypoints_basic(monkeypatch):
    """entry_points 发现产 PluginSpec"""
    cfg = _config_with()
    discovery = PluginDiscovery(cfg)

    fake_eps = [_fake_ep("ep_test", _EPPlugin)]
    monkeypatch.setattr(
        "merco.plugins.discovery.entry_points",
        lambda group: fake_eps if group == "merco.plugins" else [],
    )

    specs = discovery.discover()
    assert len(specs) == 1
    s = specs[0]
    assert s.name == "ep_test"
    assert s.source == "entrypoint"
    assert s.priority == 60          # 从类属性读
    assert s.version == "1.0.0"
    assert s.load_cls() is _EPPlugin


def test_discover_entrypoints_reads_priority_from_class(monkeypatch):
    """entry_points 的 priority/depends_on 从 Plugin 类属性读"""
    cfg = _config_with()
    discovery = PluginDiscovery(cfg)

    class WithDeps(Plugin):
        name = "with_deps"
        priority = 90
        depends_on = ["ep_test"]
        async def activate(self, ctx): ...

    class Dep(Plugin):
        name = "ep_test"
        version = "1.0.0"
        async def activate(self, ctx): ...

    monkeypatch.setattr(
        "merco.plugins.discovery.entry_points",
        lambda group: [_fake_ep("with_deps", WithDeps), _fake_ep("ep_test", Dep)] if group == "merco.plugins" else [],
    )
    specs = discovery.discover()
    assert len(specs) == 2
    spec_with_deps = [s for s in specs if s.name == "with_deps"][0]
    assert spec_with_deps.priority == 90
    assert spec_with_deps.depends_on == ["ep_test"]


def _write_dir_plugin(tmp_path, name, entry="main:MyPlugin", priority=50, depends_on=None):
    """在 tmp_path/<name>/ 下造一个目录扫描插件"""
    pdir = tmp_path / name
    pdir.mkdir()
    (pdir / "plugin.toml").write_text(
        f'[plugin]\nname = "{name}"\nversion = "0.1.0"\n'
        f'description = "d"\npriority = {priority}\n'
        f'depends_on = {depends_on or []}\nentry = "{entry}"\n', encoding="utf-8"
    )
    (pdir / "main.py").write_text(
        "from merco.plugins.base import Plugin\n"
        f"class MyPlugin(Plugin):\n"
        f'    name = "{name}"\n    version = "0.1.0"\n'
        "    async def activate(self, ctx): ...\n",
        encoding="utf-8",
    )
    return pdir


def test_discover_dir_scan_basic(tmp_path, monkeypatch):
    """目录扫描发现 plugin.toml 插件"""
    _write_dir_plugin(tmp_path, "myplug", priority=55)
    cfg = _config_with(paths=[str(tmp_path)])
    discovery = PluginDiscovery(cfg)
    monkeypatch.setattr("merco.plugins.discovery.entry_points", lambda group: [])

    specs = discovery.discover()
    assert len(specs) == 1
    s = specs[0]
    assert s.name == "myplug"
    assert s.source == "dir"
    assert s.priority == 55  # 从 toml 读，不被 class default 50 覆盖
    assert s.instantiate().name == "myplug"


def test_discover_dir_scan_skips_dir_without_toml(tmp_path, monkeypatch):
    """无 plugin.toml 的目录静默跳过"""
    (tmp_path / "not_a_plugin").mkdir()
    (tmp_path / "not_a_plugin" / "readme.txt").write_text("hi")
    _write_dir_plugin(tmp_path, "real")
    cfg = _config_with(paths=[str(tmp_path)])
    discovery = PluginDiscovery(cfg)
    monkeypatch.setattr("merco.plugins.discovery.entry_points", lambda group: [])

    specs = discovery.discover()
    assert [s.name for s in specs] == ["real"]


def test_discover_dir_scan_bad_toml_skipped(tmp_path, monkeypatch, caplog):
    """plugin.toml 解析失败 -> warn + 跳过"""
    pdir = tmp_path / "bad"
    pdir.mkdir()
    (pdir / "plugin.toml").write_text("not = valid = toml = ==", encoding="utf-8")
    _write_dir_plugin(tmp_path, "good")
    cfg = _config_with(paths=[str(tmp_path)])
    discovery = PluginDiscovery(cfg)
    monkeypatch.setattr("merco.plugins.discovery.entry_points", lambda group: [])

    with caplog.at_level("WARNING"):
        specs = discovery.discover()
    assert [s.name for s in specs] == ["good"]
    assert any("bad" in r.message for r in caplog.records)


def test_dir_overrides_entrypoint(tmp_path, monkeypatch):
    """同名时 dir-scan 覆盖 entry_points"""
    _write_dir_plugin(tmp_path, "shared", priority=99)
    cfg = _config_with(paths=[str(tmp_path)])
    discovery = PluginDiscovery(cfg)

    class EPVer(Plugin):
        name = "shared"
        priority = 10
        async def activate(self, ctx): ...

    monkeypatch.setattr(
        "merco.plugins.discovery.entry_points",
        lambda group: [_fake_ep("shared", EPVer)] if group == "merco.plugins" else [],
    )
    specs = {s.name: s for s in discovery.discover()}
    assert specs["shared"].source == "dir"
    assert specs["shared"].priority == 99  # dir 的，不是 EP 的 10


def test_disabled_plugin_not_loaded(monkeypatch):
    """disabled 插件不进入 specs（不 load_cls）"""
    cfg = _config_with(plugins={"ep_test": {"enabled": False}})
    discovery = PluginDiscovery(cfg)
    monkeypatch.setattr(
        "merco.plugins.discovery.entry_points",
        lambda group: [_fake_ep("ep_test", _EPPlugin)] if group == "merco.plugins" else [],
    )
    specs = discovery.discover()
    assert all(s.name != "ep_test" for s in specs)


def test_missing_dep_pruned(monkeypatch, caplog):
    """depends_on 引用不存在的插件 -> 剪枝"""
    class WithMissing(Plugin):
        name = "needs_ghost"
        depends_on = ["ghost"]
        async def activate(self, ctx): ...

    cfg = _config_with()
    discovery = PluginDiscovery(cfg)
    monkeypatch.setattr(
        "merco.plugins.discovery.entry_points",
        lambda group: [_fake_ep("needs_ghost", WithMissing)] if group == "merco.plugins" else [],
    )
    with caplog.at_level("WARNING"):
        specs = discovery.discover()
    assert specs == []
    assert any("ghost" in r.message for r in caplog.records)


def test_circular_dep_skipped(monkeypatch, caplog):
    """循环依赖 -> 检测 warn + 跳过涉及插件"""
    class A(Plugin):
        name = "circ_a"
        depends_on = ["circ_b"]
        async def activate(self, ctx): ...

    class B(Plugin):
        name = "circ_b"
        depends_on = ["circ_a"]
        async def activate(self, ctx): ...

    cfg = _config_with()
    discovery = PluginDiscovery(cfg)
    monkeypatch.setattr(
        "merco.plugins.discovery.entry_points",
        lambda group: [_fake_ep("circ_a", A), _fake_ep("circ_b", B)] if group == "merco.plugins" else [],
    )
    with caplog.at_level("WARNING"):
        specs = discovery.discover()
    # 两个循环插件都被跳过
    assert specs == []
    assert any("circular" in r.message for r in caplog.records)


def test_builtin_entrypoints_discoverable():
    """真实 entry_points：7 个 builtin 都能被发现且 priority 正确"""
    cfg = _config_with()  # uses MagicMock config — not used here
    from merco.plugins.discovery import PluginDiscovery
    discovery = PluginDiscovery(cfg)
    specs = {s.name: s for s in discovery.discover()}
    expected = {
        "observability": 100, "skills": 60, "mcp": 50,
        "subagent": 40, "web": 30, "scheduler": 20, "superpower": 10,
    }
    for name, prio in expected.items():
        assert name in specs, f"missing builtin {name}"
        assert specs[name].priority == prio, f"{name} priority={specs[name].priority} != {prio}"
        assert specs[name].source == "entrypoint"
