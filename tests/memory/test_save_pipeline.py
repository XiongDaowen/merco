"""MemorySavePipeline 单测"""
import pytest
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


import pytest
from merco.memory.save_pipeline import SourceEnricher


@pytest.mark.asyncio
async def test_source_enricher_adds_prefix_tag():
    """SourceEnricher 自动补 [source] 前缀到 tags"""
    enricher = SourceEnricher()
    item = SaveItem(key="k1", value="v1", source="user", tags=["custom"])
    result = await enricher.process(item)
    assert result is not None
    assert "[user]" in result.tags
    assert "custom" in result.tags
    assert result.tags[0] == "[user]"


@pytest.mark.asyncio
async def test_source_enricher_does_not_duplicate_prefix():
    """已含 [source] 前缀时不重复加"""
    enricher = SourceEnricher()
    item = SaveItem(key="k1", value="v1", source="user", tags=["[user]", "x"])
    result = await enricher.process(item)
    assert result is not None
    assert result.tags.count("[user]") == 1
