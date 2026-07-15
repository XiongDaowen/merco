"""上下文压缩处理器单元测试"""
import pytest
from unittest.mock import MagicMock, AsyncMock
from merco.context.processors.compress import CompressProcessor


class TestCompressProcessor:
    """CompressProcessor 测试"""

    @pytest.fixture
    def processor(self):
        """创建处理器实例"""
        return CompressProcessor(max_tokens=1000, threshold=0.75)

    @pytest.fixture
    def mock_msg_tokens(self, monkeypatch):
        """Mock msg_tokens 函数"""
        def mock_tokens(msg):
            # 简单模拟：每条消息固定 100 tokens
            return 100
        monkeypatch.setattr("merco.context.processors.compress.msg_tokens", mock_tokens)

    @pytest.mark.asyncio
    async def test_trigger_threshold(self, processor, mock_msg_tokens):
        """测试压缩触发阈值"""
        # 7 条消息：700 tokens，刚好等于阈值（1000 * 0.75 = 750）以下，不触发
        messages = [{"role": "user", "content": f"msg {i}"} for i in range(7)]
        result = await processor.process(messages)
        assert len(result) == 7  # 未压缩

        # 8 条消息：800 tokens，超过阈值，触发压缩
        messages = [{"role": "user", "content": f"msg {i}"} for i in range(8)]
        result = await processor.process(messages)
        assert len(result) < 8  # 已压缩

    @pytest.mark.asyncio
    async def test_not_trigger_when_few_messages(self, processor, monkeypatch):
        """测试消息太少时不压缩（<=4条）"""
        # 4 条消息，即使 token 超过阈值也不压缩
        messages = [{"role": "user", "content": f"msg {i}"} for i in range(4)]
        # Mock 每条消息 300 tokens，总 1200 > 750
        def mock_large_tokens(msg):
            return 300
        monkeypatch.setattr("merco.context.processors.compress.msg_tokens", mock_large_tokens)

        result = await processor.process(messages)
        assert len(result) == 4  # 未压缩

    @pytest.mark.asyncio
    async def test_sliding_window_strategy(self, processor, mock_msg_tokens):
        """测试滑动窗口压缩策略"""
        # 创建 10 条消息，交替 user/assistant
        messages = []
        for i in range(10):
            role = "user" if i % 2 == 0 else "assistant"
            messages.append({"role": role, "content": f"msg {i}"})

        result = await processor.process(messages, compress_strategy="sliding")

        # 应该保留最后 2 轮（4条消息） + 1 条摘要 = 5 条
        assert len(result) == 5
        # 第一条应该是摘要
        assert "压缩了 6 条历史消息" in result[0]["content"]
        # 后面 4 条是最后 2 轮
        assert result[1]["content"] == "msg 6"
        assert result[2]["content"] == "msg 7"
        assert result[3]["content"] == "msg 8"
        assert result[4]["content"] == "msg 9"

    @pytest.mark.asyncio
    async def test_sliding_window_with_summary_fn(self, processor, mock_msg_tokens):
        """测试使用自定义 summary_fn"""
        messages = []
        for i in range(10):
            role = "user" if i % 2 == 0 else "assistant"
            messages.append({"role": role, "content": f"msg {i}"})

        # Mock 摘要函数
        mock_summary = AsyncMock(return_value="Custom summary of old messages")
        result = await processor.process(messages, compress_strategy="sliding", summary_fn=mock_summary)

        mock_summary.assert_called_once()
        # 第一条应该是自定义摘要
        assert result[0]["content"] == "Custom summary of old messages"

    @pytest.mark.asyncio
    async def test_truncate_strategy(self, processor, mock_msg_tokens):
        """测试截断策略"""
        # 创建 10 条消息
        messages = []
        for i in range(10):
            role = "user" if i % 2 == 0 else "assistant"
            messages.append({"role": role, "content": f"msg {i}"})

        result = await processor.process(messages, compress_strategy="truncate")

        # 应该保留最后 6 条
        assert len(result) == 6
        assert result[0]["content"] == "msg 4"
        assert result[-1]["content"] == "msg 9"

    def test_orphan_tool_message_handling(self, processor):
        """测试孤立工具消息处理"""
        # 创建消息链，其中工具消息在截断边界
        messages = [
            {"role": "user", "content": "msg 0"},
            {"role": "assistant", "content": "msg 1", "tool_calls": [{"id": "1", "function": {"name": "tool1", "arguments": "{}"}}]},
            {"role": "tool", "content": "tool result 1", "tool_call_id": "1"},
            {"role": "assistant", "content": "msg 3"},
            {"role": "user", "content": "msg 4"},
            {"role": "assistant", "content": "msg 5", "tool_calls": [{"id": "2", "function": {"name": "tool2", "arguments": "{}"}}]},
            {"role": "tool", "content": "tool result 2", "tool_call_id": "2"},
            {"role": "assistant", "content": "msg 7"},
        ]

        # 截断策略会保留最后 6 条，即从 msg 2 开始，但 msg 2 是 tool 消息，需要补全前面的 tool_call
        result = processor._truncate(messages)

        # 应该包含 tool 消息对应的 assistant tool_call
        tool_msg_idx = None
        for i, msg in enumerate(result):
            if msg.get("role") == "tool" and msg["content"] == "tool result 2":
                tool_msg_idx = i
                break

        assert tool_msg_idx is not None
        # 前一条应该是对应的 assistant 消息
        prev_msg = result[tool_msg_idx - 1]
        assert prev_msg["role"] == "assistant"
        assert "tool_calls" in prev_msg
        assert prev_msg["tool_calls"][0]["id"] == "2"

    def test_build_fallback_summary(self, processor):
        """测试 fallback 摘要构建"""
        messages = [
            {"role": "user", "content": "Hello, how are you?"},
            {"role": "assistant", "content": "I'm good, thanks!"},
            {"role": "user", "content": "What's the weather today?"},
            {"role": "assistant", "content": "It's sunny!"},
        ]

        summary = processor._build_summary(messages)
        assert summary["role"] == "system"
        assert "压缩了 4 条历史消息" in summary["content"]
        assert "Hello, how are you?" in summary["content"]
        assert "What's the weather today?" in summary["content"]

    def test_build_summary_too_many_user_messages(self, processor):
        """测试用户消息超过 5 条时只显示最后 5 条"""
        messages = []
        for i in range(10):
            messages.append({"role": "user", "content": f"User message {i}"})

        summary = processor._build_summary(messages)
        assert "最近讨论:" in summary["content"]
        # 应该只包含最后 5 条
        for i in range(5, 10):
            assert f"User message {i}"[:60] in summary["content"]
        for i in range(0, 5):
            assert f"User message {i}" not in summary["content"]
