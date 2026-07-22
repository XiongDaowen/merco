"""PluginDiscovery 单元测试"""
import pytest
from unittest.mock import patch, MagicMock
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
