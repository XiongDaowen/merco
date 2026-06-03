"""InterruptCleanupPipeline 单元测试"""

import pytest

from unittest.mock import AsyncMock, MagicMock

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


@pytest.mark.asyncio
async def test_inject_cancel_messages():
    """InjectCancelMessages 为孤儿 tool_calls 注入取消消息。"""
    from merco.core.interrupt import InjectCancelMessages

    agent = MagicMock()
    agent.context.messages = [
        {"role": "assistant", "tool_calls": [{"id": "tc_1"}, {"id": "tc_2"}]},
        {"role": "tool", "tool_call_id": "tc_1", "content": "result"},
    ]
    agent.session = MagicMock()

    ctx = CleanupContext(
        agent=agent,
        cancelled_tool_calls=[{"id": "tc_2"}],
        session_id="test"
    )

    processor = InjectCancelMessages()
    result = await processor.process(ctx)

    assert result is False  # 不停止管线
    agent.context.add.assert_called()
    agent.session.add_message.assert_called()


@pytest.mark.asyncio
async def test_terminate_subprocesses():
    """TerminateSubprocesses kill 所有运行中的子进程。"""
    from merco.core.interrupt import TerminateSubprocesses

    proc1 = MagicMock()
    proc2 = MagicMock()
    bash_tool = MagicMock()
    bash_tool._active_processes = {proc1, proc2}

    agent = MagicMock()
    agent.tool_registry.get.return_value = bash_tool

    ctx = CleanupContext(agent=agent, cancelled_tool_calls=[], session_id="test")

    processor = TerminateSubprocesses()
    result = await processor.process(ctx)

    assert result is False
    proc1.kill.assert_called_once()
    proc2.kill.assert_called_once()
    assert len(bash_tool._active_processes) == 0


@pytest.mark.asyncio
async def test_close_mcp_connections():
    """CloseMCPConnections 关闭 MCP 连接。"""
    from merco.core.interrupt import CloseMCPConnections

    agent = MagicMock()
    agent.mcp_manager = MagicMock()
    agent.mcp_manager.shutdown = AsyncMock()

    ctx = CleanupContext(agent=agent, cancelled_tool_calls=[], session_id="test")

    processor = CloseMCPConnections()
    result = await processor.process(ctx)

    assert result is False
    agent.mcp_manager.shutdown.assert_called_once()


@pytest.mark.asyncio
async def test_emit_interrupt_hooks():
    """EmitInterruptHooks 发射中断钩子。"""
    from merco.core.interrupt import EmitInterruptHooks

    agent = MagicMock()
    agent.hooks.emit = AsyncMock()

    ctx = CleanupContext(
        agent=agent,
        cancelled_tool_calls=[{"id": "tc_1"}],
        session_id="test"
    )

    processor = EmitInterruptHooks()
    result = await processor.process(ctx)

    assert result is False
    agent.hooks.emit.assert_called_with(
        "agent.interrupted",
        interrupted_tools=1,
        session_id="test"
    )


@pytest.mark.asyncio
async def test_save_partial_state():
    """SavePartialState 保存 session + observer 快照。"""
    from merco.core.interrupt import SavePartialState

    agent = MagicMock()
    agent.observer = MagicMock()
    agent.session = MagicMock()
    agent._session_store = MagicMock()

    ctx = CleanupContext(agent=agent, cancelled_tool_calls=[], session_id="test")

    processor = SavePartialState()
    result = await processor.process(ctx)

    assert result is False
    agent.observer.save.assert_called_once()
    agent.session.save.assert_called_once()
    agent._session_store.save_metadata.assert_called_once()
