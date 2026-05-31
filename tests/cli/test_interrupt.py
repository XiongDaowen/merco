"""InterruptPipeline 单元测试"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from cli.interrupt import InterruptContext, InterruptPipeline, InterruptState, InterruptStrategy


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


@pytest.mark.asyncio
async def test_cancel_task_strategy_running():
    """CancelTaskStrategy 在 AGENT_RUNNING 状态下取消任务。"""
    from cli.interrupt import CancelTaskStrategy

    task = MagicMock()
    task.done.return_value = False
    task.cancel = MagicMock()

    ctx = InterruptContext(state=InterruptState.AGENT_RUNNING, task=task)
    strategy = CancelTaskStrategy()

    result = await strategy.handle(ctx)

    assert result is True
    assert ctx.handled is True
    task.cancel.assert_called_once()


@pytest.mark.asyncio
async def test_cancel_task_strategy_not_running():
    """CancelTaskStrategy 在非 AGENT_RUNNING 状态下跳过。"""
    from cli.interrupt import CancelTaskStrategy

    ctx = InterruptContext(state=InterruptState.IDLE)
    strategy = CancelTaskStrategy()

    result = await strategy.handle(ctx)

    assert result is False


@pytest.mark.asyncio
async def test_cancel_task_strategy_prevent_reentry():
    """CancelTaskStrategy 防止重入。"""
    from cli.interrupt import CancelTaskStrategy

    task = MagicMock()

    ctx = InterruptContext(state=InterruptState.AGENT_RUNNING, task=task)
    strategy = CancelTaskStrategy()

    result1 = await strategy.handle(ctx)
    assert result1 is True
    task.cancel.assert_called_once()

    # 同一任务再次中断，不应重复 cancel
    result2 = await strategy.handle(ctx)
    assert result2 is True
    task.cancel.assert_called_once()


@pytest.mark.asyncio
async def test_clear_input_strategy():
    """ClearInputStrategy 清空输入缓冲区。"""
    from cli.interrupt import ClearInputStrategy

    on_clear = MagicMock()
    ctx = InterruptContext(state=InterruptState.INPUT_HAS_TEXT)
    strategy = ClearInputStrategy(on_clear)

    result = await strategy.handle(ctx)

    assert result is True
    assert ctx.handled is True
    on_clear.assert_called_once()


@pytest.mark.asyncio
async def test_clear_input_strategy_wrong_state():
    """ClearInputStrategy 在非 INPUT_HAS_TEXT 状态下跳过。"""
    from cli.interrupt import ClearInputStrategy

    on_clear = MagicMock()
    ctx = InterruptContext(state=InterruptState.IDLE)
    strategy = ClearInputStrategy(on_clear)

    result = await strategy.handle(ctx)

    assert result is False
    on_clear.assert_not_called()


@pytest.mark.asyncio
async def test_exit_with_hooks_strategy_first_press():
    """ExitWithHooksStrategy 第一次按下设置 exit_count。"""
    from cli.interrupt import ExitWithHooksStrategy

    on_exit = AsyncMock()
    ctx = InterruptContext(state=InterruptState.IDLE, exit_count=0)
    strategy = ExitWithHooksStrategy(on_exit)

    result = await strategy.handle(ctx)

    assert result is True
    assert ctx.exit_count == 1
    on_exit.assert_not_called()


@pytest.mark.asyncio
async def test_exit_with_hooks_strategy_second_press():
    """ExitWithHooksStrategy 第二次按下执行退出。"""
    from cli.interrupt import ExitWithHooksStrategy

    on_exit = AsyncMock()
    ctx = InterruptContext(state=InterruptState.IDLE, exit_count=1)
    strategy = ExitWithHooksStrategy(on_exit)

    result = await strategy.handle(ctx)

    assert result is True
    assert ctx.handled is True
    on_exit.assert_called_once()
