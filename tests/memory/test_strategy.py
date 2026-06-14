"""MemorySaveStrategy 单测"""
import pytest
from merco.memory.save_pipeline import SaveItem
from merco.memory.strategy import MemorySaveStrategy


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
