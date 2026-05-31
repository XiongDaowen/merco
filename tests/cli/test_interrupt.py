"""InterruptPipeline 单元测试"""

import asyncio
import pytest
from cli.interrupt import (
    InterruptState, InterruptContext, InterruptStrategy, InterruptPipeline
)


class MockStrategy(InterruptStrategy):
    """模拟策略，记录调用。"""
    name = "mock"

    def __init__(self, should_handle: bool = False):
        self.should_handle = should_handle
        self.called = False

    async def handle(self, ctx: InterruptContext) -> bool:
        self.called = True
        return self.should_handle


@pytest.mark.asyncio
async def test_pipeline_executes_strategies_in_order():
    """管线按顺序执行策略。"""
    s1 = MockStrategy(should_handle=False)
    s2 = MockStrategy(should_handle=True)
    s3 = MockStrategy(should_handle=False)

    pipeline = InterruptPipeline()
    pipeline.use(s1).use(s2).use(s3)

    ctx = InterruptContext(state=InterruptState.IDLE)
    await pipeline.process(ctx)

    assert s1.called
    assert s2.called
    assert not s3.called  # s2 已处理，s3 不应执行


@pytest.mark.asyncio
async def test_pipeline_stops_on_first_handler():
    """第一个返回 True 的策略停止管线。"""
    s1 = MockStrategy(should_handle=True)
    s2 = MockStrategy(should_handle=True)

    pipeline = InterruptPipeline()
    pipeline.use(s1).use(s2)

    ctx = InterruptContext(state=InterruptState.IDLE)
    await pipeline.process(ctx)

    assert s1.called
    assert not s2.called


@pytest.mark.asyncio
async def test_pipeline_handles_strategy_exception():
    """策略异常不应中断管线。"""

    class FailingStrategy(InterruptStrategy):
        name = "failing"

        async def handle(self, ctx: InterruptContext) -> bool:
            raise RuntimeError("test error")

    s1 = FailingStrategy()
    s2 = MockStrategy(should_handle=True)

    pipeline = InterruptPipeline()
    pipeline.use(s1).use(s2)

    ctx = InterruptContext(state=InterruptState.IDLE)
    await pipeline.process(ctx)

    assert s2.called
