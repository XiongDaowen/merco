"""中断处理集成测试"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from cli.interrupt import CancelTaskStrategy, InterruptContext, InterruptPipeline, InterruptState
from merco.core.interrupt import (
    CleanupContext,
    EmitInterruptHooks,
    InjectCancelMessages,
    InterruptCleanupPipeline,
)


@pytest.mark.asyncio
async def test_full_interrupt_flow():
    """完整中断流程：CLI 管线 → task.cancel → Agent 清理管线。"""
    agent = MagicMock()
    agent.context.messages = [
        {"role": "assistant", "tool_calls": [{"id": "tc_1"}]},
    ]
    agent.session = MagicMock()
    agent.hooks.emit = AsyncMock()
    agent.observer = MagicMock()
    agent._session_store = MagicMock()
    agent.mcp_manager = MagicMock()
    agent.mcp_manager.shutdown = AsyncMock()
    agent.tool_registry = MagicMock()
    agent.tool_registry.get.return_value = MagicMock()

    async def mock_agent_task():
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            cleanup_pipeline = InterruptCleanupPipeline()
            cleanup_pipeline.use(InjectCancelMessages())
            cleanup_pipeline.use(EmitInterruptHooks())

            ctx = CleanupContext(
                agent=agent,
                cancelled_tool_calls=[{"id": "tc_1"}],
                session_id="test"
            )
            await cleanup_pipeline.process(ctx)
            raise

    task = asyncio.create_task(mock_agent_task())
    await asyncio.sleep(0)  # 让任务启动进入 sleep

    cli_pipeline = InterruptPipeline()
    cli_pipeline.use(CancelTaskStrategy())

    ctx = InterruptContext(state=InterruptState.AGENT_RUNNING, task=task)
    await cli_pipeline.process(ctx)

    try:
        await task
    except asyncio.CancelledError:
        pass

    agent.context.add.assert_called()
    agent.hooks.emit.assert_called_with(
        "agent.interrupted",
        interrupted_tools=1,
        session_id="test"
    )
