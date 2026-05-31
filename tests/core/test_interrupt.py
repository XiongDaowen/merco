"""InterruptCleanupPipeline 单元测试"""

import pytest

from merco.core.interrupt import (
    CleanupContext,
    CleanupProcessor,
    InterruptCleanupPipeline,
)


class MockProcessor(CleanupProcessor):
    """模拟处理器，记录调用。"""
    name = "mock"

    def __init__(self, should_stop: bool = False):
        self.should_stop = should_stop
        self.called = False

    async def process(self, ctx: CleanupContext) -> bool:
        self.called = True
        return self.should_stop


@pytest.mark.asyncio
async def test_cleanup_pipeline_executes_processors_in_order():
    """管线按顺序执行处理器。"""
    p1 = MockProcessor(should_stop=False)
    p2 = MockProcessor(should_stop=True)
    p3 = MockProcessor(should_stop=False)

    pipeline = InterruptCleanupPipeline()
    pipeline.use(p1).use(p2).use(p3)

    ctx = CleanupContext(agent=None, cancelled_tool_calls=[], session_id="test")
    await pipeline.process(ctx)

    assert p1.called
    assert p2.called
    assert not p3.called


@pytest.mark.asyncio
async def test_cleanup_pipeline_handles_processor_exception():
    """处理器异常不应中断管线。"""

    class FailingProcessor(CleanupProcessor):
        name = "failing"

        async def process(self, ctx: CleanupContext) -> bool:
            raise RuntimeError("test error")

    p1 = FailingProcessor()
    p2 = MockProcessor(should_stop=True)

    pipeline = InterruptCleanupPipeline()
    pipeline.use(p1).use(p2)

    ctx = CleanupContext(agent=None, cancelled_tool_calls=[], session_id="test")
    await pipeline.process(ctx)

    assert p2.called


@pytest.mark.asyncio
async def test_empty_cleanup_pipeline():
    """空管线不应抛异常。"""
    pipeline = InterruptCleanupPipeline()
    ctx = CleanupContext(agent=None, cancelled_tool_calls=[], session_id="test")
    await pipeline.process(ctx)
