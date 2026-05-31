"""CLI 中断处理管线，统一管理 Ctrl+C 行为。"""

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Any

logger = logging.getLogger("merco.cli.interrupt")


class InterruptState(Enum):
    """中断时的系统状态。"""
    IDLE = "idle"              # 输入框为空
    INPUT_HAS_TEXT = "input"   # 输入框有内容
    AGENT_RUNNING = "agent"    # Agent 任务运行中


@dataclass
class InterruptContext:
    """中断处理上下文。"""
    state: InterruptState
    task: asyncio.Task | None = None
    exit_count: int = 0        # 二次确认计数器
    handled: bool = False


class InterruptStrategy(ABC):
    """中断处理策略基类。"""
    name: str = ""

    @abstractmethod
    async def handle(self, ctx: InterruptContext) -> bool:
        """返回 True 表示已处理，停止管线。"""
        ...


class InterruptPipeline:
    """中断处理管线。按优先级依次尝试各策略。"""

    def __init__(self):
        self._strategies: list[InterruptStrategy] = []

    def use(self, strategy: InterruptStrategy) -> "InterruptPipeline":
        self._strategies.append(strategy)
        return self

    async def process(self, ctx: InterruptContext) -> None:
        for strategy in self._strategies:
            try:
                if await strategy.handle(ctx):
                    return
            except Exception:
                logger.warning("中断策略 '%s' 异常", strategy.name, exc_info=True)
