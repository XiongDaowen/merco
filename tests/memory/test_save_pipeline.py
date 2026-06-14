"""MemorySavePipeline 单测"""
from dataclasses import dataclass
from merco.memory.save_pipeline import SaveItem, MemorySource, SOURCE_PRIORITY


def test_save_item_creation():
    """SaveItem 默认值正确"""
    item = SaveItem(key="k1", value="v1", source="user")
    assert item.key == "k1"
    assert item.value == "v1"
    assert item.source == "user"
    assert item.tags == []
    assert item.session_id == ""
    assert item.metadata == {}


def test_source_priority_ordering():
    """source 优先级 user > extracted > system"""
    assert SOURCE_PRIORITY["user"] > SOURCE_PRIORITY["extracted"]
    assert SOURCE_PRIORITY["extracted"] > SOURCE_PRIORITY["system"]
