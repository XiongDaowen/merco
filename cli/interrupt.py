"""CLI 中断处理管线，统一管理 Ctrl+C 行为。"""

import asyncio
import logging
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any

logger = logging.getLogger("merco.cli.interrupt")


class InterruptState(Enum):
    """中断时的系统状态。"""

    IDLE = "idle"  # 输入框为空
    INPUT_HAS_TEXT = "input"  # 输入框有内容
    AGENT_RUNNING = "agent"  # Agent 任务运行中


@dataclass
class InterruptContext:
    """中断处理上下文。"""

    state: InterruptState
    task: asyncio.Task | None = None
    exit_count: int = 0  # 二次确认计数器
    handled: bool = False


class InterruptStrategy(ABC):
    """中断处理策略基类。"""

    name: str = ""

    @abstractmethod
    async def handle(self, ctx: InterruptContext) -> bool:
        """异步处理中断，返回 True 表示已处理，停止管线。"""
        ...

    def handle_sync(self, ctx: InterruptContext) -> bool:
        """同步处理中断，用于信号处理器。默认调用异步版本的包装。"""
        # 默认实现：通过 asyncio.ensure_future 异步执行
        # 子类应重写此方法以提供真正的同步实现
        return False


class CancelTaskStrategy(InterruptStrategy):
    """取消运行中的 Agent 任务。"""

    name = "cancel_task"

    async def handle(self, ctx: InterruptContext) -> bool:
        if ctx.state != InterruptState.AGENT_RUNNING or not ctx.task:
            return False
        ctx.task.cancel()
        ctx.handled = True
        return True

    def handle_sync(self, ctx: InterruptContext) -> bool:
        """同步取消任务，立即生效。"""
        if ctx.state != InterruptState.AGENT_RUNNING or not ctx.task:
            return False
        ctx.task.cancel()
        ctx.handled = True
        return True


class ClearInputStrategy(InterruptStrategy):
    """清空输入框。"""

    name = "clear_input"

    def __init__(self, on_clear: Callable[[], None]):
        self._on_clear = on_clear

    async def handle(self, ctx: InterruptContext) -> bool:
        if ctx.state != InterruptState.INPUT_HAS_TEXT:
            return False
        self._on_clear()
        ctx.handled = True
        return True

    def handle_sync(self, ctx: InterruptContext) -> bool:
        """同步清空输入框。"""
        if ctx.state != InterruptState.INPUT_HAS_TEXT:
            return False
        self._on_clear()
        ctx.handled = True
        return True


class ExitWithHooksStrategy(InterruptStrategy):
    """优雅退出。"""

    name = "exit_with_hooks"

    def __init__(self, on_exit: Callable[[], Any]):
        self._on_exit = on_exit

    async def handle(self, ctx: InterruptContext) -> bool:
        if ctx.state != InterruptState.IDLE:
            return False
        if ctx.exit_count == 0:
            ctx.exit_count = 1
            return True
        ctx.handled = True
        await self._on_exit()
        return True

    def handle_sync(self, ctx: InterruptContext) -> bool:
        """同步退出。"""
        if ctx.state != InterruptState.IDLE:
            return False
        if ctx.exit_count == 0:
            ctx.exit_count = 1
            return True
        ctx.handled = True
        self._on_exit()
        return True


class InterruptPipeline:
    """中断处理管线。按优先级依次尝试各策略。"""

    def __init__(self):
        self._strategies: list[InterruptStrategy] = []

    def use(self, strategy: InterruptStrategy) -> "InterruptPipeline":
        self._strategies.append(strategy)
        return self

    async def process(self, ctx: InterruptContext) -> None:
        """异步执行管线。"""
        for strategy in self._strategies:
            try:
                if await strategy.handle(ctx):
                    return
            except Exception:
                logger.warning("中断策略 '%s' 异常", strategy.name, exc_info=True)

    def process_sync(self, ctx: InterruptContext) -> None:
        """同步执行管线，用于信号处理器。"""
        for strategy in self._strategies:
            try:
                if strategy.handle_sync(ctx):
                    return
            except Exception:
                logger.warning("中断策略 '%s' 异常", strategy.name, exc_info=True)
