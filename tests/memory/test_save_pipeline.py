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


from merco.memory.save_pipeline import DedupProcessor


class FakeStore:
    """最小 MemoryStore mock"""
    def __init__(self, existing=None):
        self._data = existing or {}

    def load(self, key):
        return self._data.get(key)


@pytest.mark.asyncio
async def test_dedup_skip_when_existing_user_wins():
    """已有 [user] 时 [extracted] 来 → skip（保护 user）"""
    store = FakeStore({"k1": {"tags": ["[user]", "x"], "value": "old"}})
    proc = DedupProcessor(store)
    item = SaveItem(key="k1", value="new", source="extracted")
    result = await proc.process(item)
    assert result is None  # 被 skip


@pytest.mark.asyncio
async def test_dedup_overwrite_when_new_higher_priority():
    """已有 [extracted] 时 [user] 来 → 覆盖"""
    store = FakeStore({"k1": {"tags": ["[extracted]"], "value": "old"}})
    proc = DedupProcessor(store)
    item = SaveItem(key="k1", value="new", source="user")
    result = await proc.process(item)
    assert result is not None
    assert result.value == "new"


@pytest.mark.asyncio
async def test_dedup_pass_through_when_key_not_exists():
    """key 不存在 → 直接通过"""
    store = FakeStore()
    proc = DedupProcessor(store)
    item = SaveItem(key="k1", value="v", source="user")
    result = await proc.process(item)
    assert result is not None


@pytest.mark.asyncio
async def test_dedup_infer_source_from_tags():
    """旧记录无 [source] 标签时按 system 处理（向后兼容，最低优先级）"""
    store = FakeStore({"k1": {"tags": [], "value": "old"}})
    proc = DedupProcessor(store)
    # extracted 来（优先级 2） vs 空（默认最低 0） → 覆盖
    item = SaveItem(key="k1", value="new", source="extracted")
    result = await proc.process(item)
    assert result is not None


from merco.memory.save_pipeline import MemorySavePipeline, MemorySaveProcessor


class FakeHooks:
    """最小 HookRegistry mock"""
    def __init__(self):
        self.events = []

    async def emit(self, event, **kwargs):
        self.events.append((event, kwargs))


class FakeMemoryStore:
    """最小 MemoryStore mock — save + load"""
    def __init__(self):
        self._data = {}

    def save(self, key, value, tags=None):
        self._data[key] = {"value": value, "tags": tags or []}

    def load(self, key):
        return self._data.get(key)


@pytest.mark.asyncio
async def test_pipeline_saves_and_emits_event():
    """Pipeline 成功时 emit memory.saved"""
    store = FakeMemoryStore()
    hooks = FakeHooks()
    pipeline = MemorySavePipeline(store, hooks)

    item = SaveItem(key="k1", value="hello", source="user", tags=["custom"])
    result = await pipeline.save(item)
    assert result is True
    assert store._data["k1"]["value"] == "hello"
    assert "[user]" in store._data["k1"]["tags"]
    assert "custom" in store._data["k1"]["tags"]

    # 验证 emit
    assert len(hooks.events) == 1
    event, kwargs = hooks.events[0]
    assert event == "memory.saved"
    assert kwargs["key"] == "k1"
    assert kwargs["source"] == "user"


@pytest.mark.asyncio
async def test_pipeline_dedup_skip_returns_false():
    """Dedup 命中 → 返回 False，不发 memory.saved"""
    store = FakeMemoryStore()
    store._data["k1"] = {"value": "old", "tags": ["[user]"]}
    hooks = FakeHooks()
    pipeline = MemorySavePipeline(store, hooks)

    item = SaveItem(key="k1", value="new", source="extracted")
    result = await pipeline.save(item)
    assert result is False
    assert store._data["k1"]["value"] == "old"  # 未覆盖
    assert hooks.events == []


@pytest.mark.asyncio
async def test_pipeline_use_adds_processor():
    """use() 追加 processor 到链尾"""
    store = FakeMemoryStore()
    hooks = FakeHooks()
    pipeline = MemorySavePipeline(store, hooks)

    class TagProcessor(MemorySaveProcessor):
        name = "test_tag"
        async def process(self, item):
            item.tags.append("from_test")
            return item

    pipeline.use(TagProcessor())
    await pipeline.save(SaveItem(key="k1", value="v", source="user"))
    assert "from_test" in store._data["k1"]["tags"]


@pytest.mark.asyncio
async def test_pipeline_processor_exception_returns_false():
    """Processor 抛异常 → save() 返回 False 且不发 memory.saved"""
    store = FakeMemoryStore()
    hooks = FakeHooks()
    pipeline = MemorySavePipeline(store, hooks)

    class FailingProcessor(MemorySaveProcessor):
        name = "failing"
        async def process(self, item):
            raise RuntimeError("boom")

    pipeline.use(FailingProcessor())
    result = await pipeline.save(SaveItem(key="k1", value="v", source="user"))
    assert result is False
    # store 未写入
    assert "k1" not in store._data
    # 未 emit memory.saved
    assert hooks.events == []
