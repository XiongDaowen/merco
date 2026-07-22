"""PluginSpec 单元测试"""
from merco.plugins.base import Plugin, PluginSpec


class _Dummy(Plugin):
    name = "dummy"
    version = "1.0.0"
    priority = 70
    depends_on = ["other"]

    async def activate(self, ctx): ...


def _make_spec():
    return PluginSpec(
        name="dummy",
        source="entrypoint",
        version="1.0.0",
        priority=70,
        depends_on=["other"],
        loader=lambda: _Dummy,
    )


def test_spec_defaults():
    spec = PluginSpec(name="x", source="dir", loader=lambda: _Dummy)
    assert spec.priority == 50
    assert spec.depends_on == []
    assert spec.version == ""


def test_spec_load_cls_caches():
    calls = {"n": 0}

    def loader():
        calls["n"] += 1
        return _Dummy

    spec = PluginSpec(name="dummy", source="entrypoint", loader=loader)
    c1 = spec.load_cls()
    c2 = spec.load_cls()
    assert c1 is _Dummy
    assert c2 is _Dummy
    assert calls["n"] == 1  # 只调用一次


def test_spec_instantiate_returns_instance_and_caches():
    spec = _make_spec()
    inst1 = spec.instantiate()
    inst2 = spec.instantiate()
    assert isinstance(inst1, _Dummy)
    assert inst1 is inst2  # 缓存


def test_spec_no_loader_raises():
    spec = PluginSpec(name="x", source="dir")
    try:
        spec.load_cls()
        assert False, "应抛 RuntimeError"
    except RuntimeError:
        pass
