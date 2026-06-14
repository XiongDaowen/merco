"""Memory 保存触发策略 — 监听 Hook 事件，构造 SaveItem 喂给 Pipeline"""
from __future__ import annotations

import hashlib
import logging
import re
from abc import ABC, abstractmethod

from .save_pipeline import SaveItem

logger = logging.getLogger("merco.memory.strategy")


class MemorySaveStrategy(ABC):
    """监听事件，构造 SaveItem 喂给 Pipeline"""

    name: str = ""

    def __init__(self, pipeline):
        self.pipeline = pipeline

    @abstractmethod
    async def on_event(self, event: str, **kwargs) -> None: ...


class ExplicitRememberStrategy(MemorySaveStrategy):
    """/remember <text> 显式存一条记忆"""
    name = "explicit_remember"

    def subscribe(self, hooks) -> None:
        """注册到 HookRegistry"""
        hooks.on("command.remember", self._on_remember)

    async def on_event(self, event: str, **kwargs) -> None:
        """兼容直接调用（测试用）"""
        await self._on_remember(**kwargs)

    async def _on_remember(self, text: str, key: str = "", **kwargs) -> None:
        if not key:
            key = self._derive_key(text)
        item = SaveItem(key=key, value=text, source="user")
        await self.pipeline.save(item)

    @staticmethod
    def _derive_key(text: str) -> str:
        """从文本生成稳定 key: user_<前20字净化>_<hash8>"""
        h = hashlib.md5(text.encode()).hexdigest()[:8]
        prefix = re.sub(r"\W+", "_", text[:20].strip()).strip("_")
        return f"user_{prefix}_{h}" if prefix else f"user_{h}"
