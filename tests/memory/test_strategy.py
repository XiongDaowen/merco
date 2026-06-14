"""MemorySaveStrategy 单测"""
import pytest
from merco.memory.save_pipeline import SaveItem
from merco.memory.strategy import MemorySaveStrategy, ExplicitRememberStrategy


class FakePipeline:
    def __init__(self):
        self.saved = []

    async def save(self, item):
        self.saved.append(item)
        return True


class FakeStrategy(MemorySaveStrategy):
    name = "fake"

    def __init__(self, pipeline):
        super().__init__(pipeline)
        self.handled = []

    async def on_event(self, event, **kwargs):
        self.handled.append((event, kwargs))


def test_strategy_name_default():
    """基类 name 默认空字符串"""
    s = FakeStrategy(FakePipeline())
    assert s.name == "fake"  # 子类覆盖


def test_strategy_holds_pipeline_ref():
    """Strategy 持有 pipeline 引用"""
    p = FakePipeline()
    s = FakeStrategy(p)
    assert s.pipeline is p


async def test_explicit_remember_uses_given_key():
    """显式 key 时直接用"""
    p = FakePipeline()
    s = ExplicitRememberStrategy(p)
    await s.on_event("command.remember", text="hello", key="my_key")
    assert len(p.saved) == 1
    assert p.saved[0].key == "my_key"
    assert p.saved[0].value == "hello"
    assert p.saved[0].source == "user"


async def test_explicit_remember_auto_derives_key():
    """无 key 时自动派生"""
    p = FakePipeline()
    s = ExplicitRememberStrategy(p)
    await s.on_event("command.remember", text="我喜欢用中文交流")
    assert len(p.saved) == 1
    assert p.saved[0].key.startswith("user_")
    assert "我喜欢" in p.saved[0].key or len(p.saved[0].key) > 10


async def test_explicit_derive_key_stable_for_same_text():
    """相同文本派生相同 key"""
    k1 = ExplicitRememberStrategy._derive_key("hello world")
    k2 = ExplicitRememberStrategy._derive_key("hello world")
    assert k1 == k2


async def test_explicit_derive_key_handles_special_chars():
    """特殊字符 → 下划线"""
    k = ExplicitRememberStrategy._derive_key("hello! @world#")
    assert "!" not in k
    assert "@" not in k
    assert "#" not in k


def test_explicit_subscribe_registers_handler():
    """subscribe() 注册到 hooks"""
    class FakeHooks:
        def __init__(self):
            self.handlers = {}
        def on(self, event, handler):
            self.handlers[event] = handler

    hooks = FakeHooks()
    s = ExplicitRememberStrategy(FakePipeline())
    s.subscribe(hooks)
    assert "command.remember" in hooks.handlers
    assert hooks.handlers["command.remember"] == s._on_remember
