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
