"""工具精简恢复器单元测试"""
import pytest

from merco.core.pipeline import RecoveryContext
from merco.tools.recovery import ToolReduceRecovery


class TestToolReduceRecovery:
    """ToolReduceRecovery 测试"""

    @pytest.fixture
    def recovery(self):
        """创建恢复器实例"""
        return ToolReduceRecovery(min_tools=5)

    @pytest.fixture
    def recovery_ctx(self):
        """创建恢复上下文"""
        return RecoveryContext(
            error=Exception("test error"),
            compress_count=0,
            max_reduce=3,
            tool_count=10  # 当前有10个工具
        )

    @pytest.mark.asyncio
    async def test_attempt_successful_reduce(self, recovery, recovery_ctx):
        """测试成功触发工具精简"""
        result = await recovery.attempt(recovery_ctx)

        assert result is True
        assert recovery_ctx.reduce_tools is True

    @pytest.mark.asyncio
    async def test_attempt_skip_when_max_reduce_reached(self, recovery, recovery_ctx):
        """测试当达到最大恢复次数时跳过"""
        recovery_ctx.compress_count = 3  # 等于max_reduce=3

        result = await recovery.attempt(recovery_ctx)

        assert result is False
        assert recovery_ctx.reduce_tools is False  # 没有被设置

    @pytest.mark.asyncio
    async def test_attempt_skip_when_too_few_tools(self, recovery, recovery_ctx):
        """测试当工具数量已经很少时跳过"""
        recovery_ctx.tool_count = 5  # 等于min_tools=5

        result = await recovery.attempt(recovery_ctx)

        assert result is False
        assert recovery_ctx.reduce_tools is False  # 没有被设置

    @pytest.mark.asyncio
    async def test_attempt_custom_min_tools(self, recovery_ctx):
        """测试自定义最小工具数量"""
        recovery = ToolReduceRecovery(min_tools=8)
        recovery_ctx.tool_count = 7  # 少于min_tools

        result = await recovery.attempt(recovery_ctx)
        assert result is False

        recovery_ctx.tool_count = 9  # 多于min_tools
        result = await recovery.attempt(recovery_ctx)
        assert result is True
