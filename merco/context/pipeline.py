"""ContextProcessor ABC + ContextPipeline"""

from __future__ import annotations

from abc import ABC, abstractmethod


class ContextProcessor(ABC):
    """上下文处理器基类"""

    name: str = ""

    @abstractmethod
    async def process(self, messages: list[dict], **kwargs) -> list[dict]:
        """处理消息列表，返回处理后的消息列表"""
        ...


class ContextPipeline:
    """上下文处理管线 — 按注册顺序执行处理器"""

    def __init__(self):
        self._processors: list[ContextProcessor] = []

    def use(self, processor: ContextProcessor) -> ContextPipeline:
        """注册处理器"""
        self._processors.append(processor)
        return self

    async def run(self, messages: list[dict], **kwargs) -> list[dict]:
        """按顺序执行所有处理器"""
        for p in self._processors:
            messages = await p.process(messages, **kwargs)
        return messages
