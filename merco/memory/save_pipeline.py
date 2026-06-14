"""Memory 保存链 — Strategy 通过它写入 MemoryStore"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Literal

logger = logging.getLogger("merco.memory.save_pipeline")


MemorySource = Literal["user", "extracted", "system"]


SOURCE_PRIORITY: dict[str, int] = {
    "user": 3,
    "extracted": 2,
    "system": 1,
}


@dataclass
class SaveItem:
    """Pipeline 输入单元"""
    key: str
    value: str
    source: MemorySource
    tags: list[str] = field(default_factory=list)
    session_id: str = ""
    metadata: dict = field(default_factory=dict)


class MemorySaveProcessor(ABC):
    """保存链处理器基类"""
    name: str = ""

    @abstractmethod
    async def process(self, item: SaveItem) -> SaveItem | None:
        """返回 None = 跳过该 item"""
        ...


class SourceEnricher(MemorySaveProcessor):
    """自动补 [source] 前缀到 tags"""
    name = "source_enricher"

    async def process(self, item: SaveItem) -> SaveItem:
        prefix = f"[{item.source}]"
        if prefix not in item.tags:
            item.tags.insert(0, prefix)
        return item


class DedupProcessor(MemorySaveProcessor):
    """按 source 优先级 skip 已有 key"""
    name = "dedup"

    def __init__(self, store):
        self._store = store

    async def process(self, item: SaveItem) -> SaveItem | None:
        existing = self._store.load(item.key)
        if not existing:
            return item
        existing_tags = existing.get("tags", []) or []
        existing_source = self._infer_source(existing_tags)
        new_priority = SOURCE_PRIORITY.get(item.source, 0)
        existing_priority = SOURCE_PRIORITY.get(existing_source, 0)
        if new_priority <= existing_priority:
            return None
        return item

    @staticmethod
    def _infer_source(tags: list[str]) -> str:
        """从 tags 推断 source。无 [source] 标记视为 system（最低，向后兼容旧记录）"""
        for t in tags:
            if t.startswith("[") and t.endswith("]"):
                inner = t[1:-1]
                if inner in SOURCE_PRIORITY:
                    return inner
        return "system"
