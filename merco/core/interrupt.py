"""Agent 中断清理管线，处理中断时的资源清理。"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("merco.core.interrupt")


@dataclass
class CleanupContext:
    """中断清理上下文。"""
    agent: Any  # Agent 类型，避免循环导入
    cancelled_tool_calls: list[dict]
    session_id: str
    results: dict[str, Any] = field(default_factory=dict)


class CleanupProcessor(ABC):
    """清理处理器基类。"""
    name: str = ""

    @abstractmethod
    async def process(self, ctx: CleanupContext) -> bool:
        """返回 True 表示已处理，停止管线。"""
        ...


class InterruptCleanupPipeline:
    """中断清理管线。"""

    def __init__(self):
        self._processors: list[CleanupProcessor] = []

    def use(self, processor: CleanupProcessor) -> "InterruptCleanupPipeline":
        self._processors.append(processor)
        return self

    async def process(self, ctx: CleanupContext) -> None:
        for processor in self._processors:
            try:
                if await processor.process(ctx):
                    return
            except Exception:
                logger.warning("清理处理器 '%s' 异常", processor.name, exc_info=True)
