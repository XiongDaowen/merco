"""处理器单测"""
from merco.context.processors.compress import CompressProcessor
from merco.context.processors.cache_optimize import CacheOptimizeProcessor


class TestCompressProcessor:
    async def test_below_threshold_no_compress(self):
        """低于阈值不压缩"""
        proc = CompressProcessor(max_tokens=10000, threshold=0.75)
        msgs = [{"role": "user", "content": "hi"}]
        result = await proc.process(msgs)
        assert result == msgs

    async def test_above_threshold_compress(self):
        """超过阈值触发压缩"""
        proc = CompressProcessor(max_tokens=100, threshold=0.5)
        # 构造大消息超过阈值
        big_msg = {"role": "user", "content": "x" * 500}
        msgs = [
            {"role": "user", "content": "old1"},
            {"role": "assistant", "content": "reply1"},
            {"role": "user", "content": "old2"},
            {"role": "assistant", "content": "reply2"},
            {"role": "user", "content": "old3"},
            {"role": "assistant", "content": "reply3"},
            big_msg,
        ]
        result = await proc.process(msgs)
        assert len(result) < len(msgs)

    async def test_truncate_strategy(self):
        """truncate 策略截断消息"""
        proc = CompressProcessor(max_tokens=100, threshold=0.5)
        msgs = [{"role": "user", "content": f"msg{i}"} for i in range(10)]
        result = await proc.process(msgs, compress_strategy="truncate")
        assert len(result) <= len(msgs)


class TestCacheOptimizeProcessor:
    async def test_system_messages_first(self):
        """system 消息排在前面"""
        proc = CacheOptimizeProcessor()
        msgs = [
            {"role": "user", "content": "hi"},
            {"role": "system", "content": "system prompt"},
            {"role": "assistant", "content": "hello"},
        ]
        result = await proc.process(msgs)
        assert result[0]["role"] == "system"

    async def test_summary_messages_stable(self):
        """摘要消息视为稳定"""
        proc = CacheOptimizeProcessor()
        msgs = [
            {"role": "user", "content": "hi"},
            {"role": "system", "content": "[Earlier conversation summary] ..."},
        ]
        result = await proc.process(msgs)
        assert "[Earlier conversation summary]" in result[0]["content"]

    async def test_memory_messages_stable(self):
        """记忆消息视为稳定"""
        proc = CacheOptimizeProcessor()
        msgs = [
            {"role": "user", "content": "hi"},
            {"role": "system", "content": "[memory] user preference"},
        ]
        result = await proc.process(msgs)
        assert "[memory]" in result[0]["content"]

    async def test_empty_messages(self):
        """空消息列表"""
        proc = CacheOptimizeProcessor()
        result = await proc.process([])
        assert result == []
