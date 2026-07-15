"""上下文压缩恢复策略单元测试"""
import pytest
from unittest.mock import MagicMock
from merco.context.recovery import ContextCompressRecovery


class TestContextCompressRecovery:
    """ContextCompressRecovery 测试"""

    @pytest.fixture
    def recovery(self):
        """创建恢复策略实例"""
        return ContextCompressRecovery(min_context_bytes=30000)

    @pytest.mark.asyncio
    async def test_trigger_on_413_error(self, recovery):
        """测试 413 错误时触发压缩"""
        ctx = MagicMock()
        ctx.error = Exception("Too large")
        ctx.error.status_code = 413
        ctx.compress_count = 0
        ctx.max_compress = 2
        ctx.context_tokens = 100  # 即使很小，413 也强制触发
        ctx.extra_wait = 0.0
        ctx.compress = False

        result = await recovery.attempt(ctx)
        assert result is True
        assert ctx.compress is True
        assert ctx.extra_wait >= 0.5

    @pytest.mark.asyncio
    async def test_trigger_on_context_length_message(self, recovery):
        """测试错误消息包含 context length 时触发"""
        ctx = MagicMock()
        ctx.error = Exception("context length exceeded")
        ctx.error.status_code = 400  # 即使不是 413
        ctx.compress_count = 0
        ctx.max_compress = 2
        ctx.context_tokens = 100
        ctx.extra_wait = 0.0
        ctx.compress = False

        result = await recovery.attempt(ctx)
        assert result is True
        assert ctx.compress is True

    @pytest.mark.asyncio
    async def test_trigger_on_large_context(self, recovery):
        """测试上下文足够大时触发"""
        ctx = MagicMock()
        ctx.error = Exception("Some error")
        ctx.error.status_code = 500
        ctx.compress_count = 0
        ctx.max_compress = 2
        # 10000 tokens * 4 = 40000 bytes > 30000 threshold
        ctx.context_tokens = 10000
        ctx.extra_wait = 0.0
        ctx.compress = False

        result = await recovery.attempt(ctx)
        assert result is True
        assert ctx.compress is True

    @pytest.mark.asyncio
    async def test_not_trigger_on_small_context(self, recovery):
        """测试上下文太小时不触发"""
        ctx = MagicMock()
        ctx.error = Exception("Some error")
        ctx.error.status_code = 500
        ctx.compress_count = 0
        ctx.max_compress = 2
        # 1000 tokens * 4 = 4000 bytes < 30000 threshold
        ctx.context_tokens = 1000
        ctx.extra_wait = 0.0
        ctx.compress = False

        result = await recovery.attempt(ctx)
        assert result is False
        assert ctx.compress is False  # Should remain False

    @pytest.mark.asyncio
    async def test_not_trigger_when_max_compress_reached(self, recovery):
        """测试超过最大压缩次数时不触发"""
        ctx = MagicMock()
        ctx.error = Exception("Too large")
        ctx.error.status_code = 413
        ctx.compress_count = 2  # 已经压缩 2 次
        ctx.max_compress = 2    # 最大 2 次
        ctx.context_tokens = 10000
        ctx.extra_wait = 0.0
        ctx.compress = False

        result = await recovery.attempt(ctx)
        assert result is False
        assert ctx.compress is False  # Should remain False

    @pytest.mark.asyncio
    async def test_extra_wait_time_set(self, recovery):
        """测试正确设置额外等待时间"""
        ctx = MagicMock()
        ctx.error = Exception("Too large")
        ctx.error.status_code = 413
        ctx.compress_count = 0
        ctx.max_compress = 2
        ctx.context_tokens = 10000
        ctx.extra_wait = 0.0  # 初始没有等待

        await recovery.attempt(ctx)
        assert ctx.extra_wait == 0.5  # 设置了至少 0.5s 等待

    @pytest.mark.asyncio
    async def test_extra_wait_not_reduced(self, recovery):
        """测试不会减少已有的等待时间"""
        ctx = MagicMock()
        ctx.error = Exception("Too large")
        ctx.error.status_code = 413
        ctx.compress_count = 0
        ctx.max_compress = 2
        ctx.context_tokens = 10000
        ctx.extra_wait = 1.0  # 已经有 1s 等待

        await recovery.attempt(ctx)
        assert ctx.extra_wait == 1.0  # 保留更大的等待时间
