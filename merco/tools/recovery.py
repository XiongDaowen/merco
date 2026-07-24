"""ToolReduceRecovery — reduces tools when context is too large."""

from __future__ import annotations

from merco.core.pipeline import Recovery, RecoveryContext


class ToolReduceRecovery(Recovery):
    """精简工具：上下文过大时关闭非关键工具集 [框架预留]

    需要 Agent 支持 reduce_tools 标志位后启用。
    """

    name = "reduce_tools"

    def __init__(self, min_tools: int = 5):
        self.min_tools = min_tools

    async def attempt(self, ctx: RecoveryContext) -> bool:
        if ctx.compress_count >= ctx.max_reduce:
            return False
        if ctx.tool_count <= self.min_tools:
            return False  # 工具已经很少，不再精简
        ctx.reduce_tools = True
        return True
