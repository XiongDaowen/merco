"""Memory 保存触发策略 — 监听 Hook 事件，构造 SaveItem 喂给 Pipeline"""
from __future__ import annotations

from abc import ABC, abstractmethod


class MemorySaveStrategy(ABC):
    """监听事件，构造 SaveItem 喂给 Pipeline"""

    name: str = ""

    def __init__(self, pipeline):
        self.pipeline = pipeline

    @abstractmethod
    async def on_event(self, event: str, **kwargs) -> None: ...
