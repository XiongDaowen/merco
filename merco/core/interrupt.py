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


class InjectCancelMessages(CleanupProcessor):
    """为孤儿 tool_calls 注入取消消息。"""

    name = "inject_cancel"

    async def process(self, ctx: CleanupContext) -> bool:
        completed_ids = set()
        for msg in ctx.agent.context.messages:
            if msg.get("tool_call_id"):
                completed_ids.add(msg["tool_call_id"])

        for msg in reversed(ctx.agent.context.messages):
            if msg.get("role") != "assistant":
                continue
            for tc in msg.get("tool_calls") or []:
                tc_id = tc.get("id") if isinstance(tc, dict) else None
                if tc_id and tc_id not in completed_ids:
                    tool_msg = {"role": "tool", "tool_call_id": tc_id, "content": "取消 (Ctrl+C)"}
                    ctx.agent.context.add(tool_msg)
                    ctx.agent.session.add_message("tool", "取消 (Ctrl+C)", tool_call_id=tc_id)
        return False


class TerminateSubprocesses(CleanupProcessor):
    """kill 所有运行中的子进程。"""

    name = "kill_subprocesses"

    async def process(self, ctx: CleanupContext) -> bool:
        bash_tool = ctx.agent.tool_registry.get("bash") if ctx.agent.tool_registry else None
        if bash_tool and hasattr(bash_tool, "_active_processes"):
            for proc in list(bash_tool._active_processes):
                proc.kill()
            bash_tool._active_processes.clear()
        return False


class CloseMCPConnections(CleanupProcessor):
    """关闭 MCP 连接。"""

    name = "close_mcp"

    async def process(self, ctx: CleanupContext) -> bool:
        if ctx.agent.mcp_manager:
            await ctx.agent.mcp_manager.shutdown()
        return False


class EmitInterruptHooks(CleanupProcessor):
    """发射中断钩子。"""

    name = "emit_hooks"

    async def process(self, ctx: CleanupContext) -> bool:
        await ctx.agent.hooks.emit(
            "agent.interrupted",
            interrupted_tools=len(ctx.cancelled_tool_calls),
            session_id=ctx.session_id,
        )
        return False


class SavePartialState(CleanupProcessor):
    """保存 session + observer 快照。"""

    name = "save_state"

    async def process(self, ctx: CleanupContext) -> bool:
        ctx.agent.observer.save()
        ctx.agent.session.metadata["observer"] = ctx.agent.observer.snapshot()
        ctx.agent.session.save()
        ctx.agent._session_store.save_metadata(ctx.agent.session.id, ctx.agent.session.metadata)
        return False


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
