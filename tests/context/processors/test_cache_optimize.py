"""缓存优化处理器单元测试"""

import pytest

from merco.context.processors.cache_optimize import CacheOptimizeProcessor


class TestCacheOptimizeProcessor:
    """CacheOptimizeProcessor 测试"""

    @pytest.fixture
    def processor(self):
        """创建处理器实例"""
        return CacheOptimizeProcessor()

    @pytest.mark.asyncio
    async def test_system_message_first(self, processor):
        """测试系统消息排在最前面"""
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "system", "content": "You are a helpful assistant"},
            {"role": "assistant", "content": "Hi there!"},
        ]

        result = await processor.process(messages)
        assert result[0]["role"] == "system"
        assert result[0]["content"] == "You are a helpful assistant"

    @pytest.mark.asyncio
    async def test_summary_message_first(self, processor):
        """测试包含 "[Earlier conversation summary]" 的消息排在前面"""
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "system", "content": "[Earlier conversation summary] We talked about weather"},
            {"role": "assistant", "content": "Hi there!"},
        ]

        result = await processor.process(messages)
        assert "[Earlier conversation summary]" in result[0]["content"]

    @pytest.mark.asyncio
    async def test_memory_message_first(self, processor):
        """测试包含 "[memory]" 的消息排在前面"""
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "system", "content": "[memory] User likes cats"},
            {"role": "assistant", "content": "Hi there!"},
        ]

        result = await processor.process(messages)
        assert "[memory]" in result[0]["content"]

    @pytest.mark.asyncio
    async def test_multiple_stable_messages(self, processor):
        """测试多个稳定消息都排在前面，保持相对顺序"""
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "system", "content": "System prompt 1"},
            {"role": "assistant", "content": "Hi"},
            {"role": "system", "content": "[memory] User info"},
            {"role": "user", "content": "How are you?"},
            {"role": "system", "content": "[Earlier conversation summary] Old chat"},
        ]

        result = await processor.process(messages)
        # 前三条应该都是稳定消息，保持原来的相对顺序
        assert result[0]["content"] == "System prompt 1"
        assert result[1]["content"] == "[memory] User info"
        assert result[2]["content"] == "[Earlier conversation summary] Old chat"
        # 后面是 volatile 消息
        assert result[3]["content"] == "Hello"
        assert result[4]["content"] == "Hi"
        assert result[5]["content"] == "How are you?"

    @pytest.mark.asyncio
    async def test_no_stable_messages(self, processor):
        """测试没有稳定消息时保持原顺序"""
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
            {"role": "user", "content": "How are you?"},
            {"role": "assistant", "content": "I'm good, thanks!"},
        ]

        result = await processor.process(messages)
        assert result == messages  # 顺序不变

    def test_is_stable_detection(self, processor):
        """测试稳定消息识别逻辑"""
        # 系统消息
        assert processor._is_stable({"role": "system", "content": "test"}) is True
        # 包含摘要标记
        assert processor._is_stable({"role": "user", "content": "[Earlier conversation summary] test"}) is True
        # 包含 memory 标记
        assert processor._is_stable({"role": "assistant", "content": "[memory] test"}) is True
        # 普通用户消息
        assert processor._is_stable({"role": "user", "content": "test"}) is False
        # 普通 assistant 消息
        assert processor._is_stable({"role": "assistant", "content": "test"}) is False
        # 工具消息
        assert processor._is_stable({"role": "tool", "content": "test"}) is False
