"""LLM 客户端单元测试"""
import pytest
from unittest.mock import MagicMock
from merco.core.llm._client import (
    _clean_surrogates,
    _strip_think_tags,
    _clean_content,
    _extract_usage,
    ThinkTagStrategy,
    DirectFieldStrategy,
    ModelExtraStrategy,
    ThinkingExtractor,
    LLMClient,
)


class TestSurrogateCleaning:
    """代理对字符清理测试"""

    def test_clean_surrogates_string(self):
        """测试清理字符串中的代理对"""
        # 包含孤立代理对的字符串 (U+D800 是高代理，U+DC00 是低代理，单独出现都是无效的)
        dirty = "Hello \ud800 World \udc00"
        clean = _clean_surrogates(dirty)
        assert clean == "Hello  World "

    def test_clean_surrogates_list(self):
        """测试清理列表中的代理对"""
        dirty = ["Hello \ud800", "World \udc00"]
        clean = _clean_surrogates(dirty)
        assert clean == ["Hello ", "World "]

    def test_clean_surrogates_dict(self):
        """测试清理字典中的代理对"""
        dirty = {"key1": "Hello \ud800", "key2": {"nested": "World \udc00"}}
        clean = _clean_surrogates(dirty)
        assert clean == {"key1": "Hello ", "key2": {"nested": "World "}}

    def test_clean_surrogates_no_change(self):
        """测试没有代理对的字符串不被修改"""
        original = "Hello World! 123 中文 🍺"
        clean = _clean_surrogates(original)
        assert clean == original


class TestThinkTagHandling:
    """Think 标签处理测试"""

    def test_strip_think_tags_standard(self):
        """测试标准 <think> 标签清理"""
        text = "<think>This is thinking</think>Hello World"
        cleaned = _strip_think_tags(text)
        assert cleaned == "Hello World"

    def test_strip_think_tags_alternate(self):
        """测试 [/think] 格式标签清理"""
        text = "<think>This is thinking[/think]Hello World"
        cleaned = _strip_think_tags(text)
        assert cleaned == "Hello World"

    def test_strip_think_tags_thinking(self):
        """测试 <thinking> 标签清理"""
        text = "<thinking>This is thinking</thinking>Hello World"
        cleaned = _strip_think_tags(text)
        assert cleaned == "Hello World"

    def test_strip_think_tags_multiple(self):
        """测试多个 think 块清理"""
        text = "<think>1</think>Hi <think>2</think>There"
        cleaned = _strip_think_tags(text)
        assert cleaned == "Hi There"

    def test_strip_think_tags_case_insensitive(self):
        """测试大小写不敏感"""
        text = "<THINK>This is thinking</THINK>Hello World"
        cleaned = _strip_think_tags(text)
        assert cleaned == "Hello World"

    def test_strip_think_tags_orphan_open(self):
        """测试孤儿开标签清理"""
        text = "<think>This is thinkingHello World"
        cleaned = _strip_think_tags(text)
        assert cleaned == "This is thinkingHello World"  # 只移除标签，保留内容

    def test_strip_think_tags_orphan_close(self):
        """测试孤儿闭标签清理"""
        text = "This is thinking</think>Hello World"
        cleaned = _strip_think_tags(text)
        assert cleaned == "This is thinkingHello World"  # 只移除标签，保留内容

    def test_clean_content(self):
        """测试完整内容清理（去标签+去前后空白）"""
        text = "  <think>This is thinking</think>  Hello World  "
        cleaned = _clean_content(text)
        assert cleaned == "Hello World"


class TestThinkTagStrategy:
    """ThinkTagStrategy 策略测试"""

    def test_extract_from_message_standard(self):
        """测试从完整消息中提取标准 think 标签"""
        strategy = ThinkTagStrategy()
        message = MagicMock()
        message.content = "<think>This is my reasoning</think>And this is the answer"

        result = strategy.extract_from_message(message)
        assert result is not None
        assert result["reasoning"] == "This is my reasoning"
        assert result["content"] == "And this is the answer"

    def test_extract_from_message_alternate_close(self):
        """测试提取 [/think] 格式的标签"""
        strategy = ThinkTagStrategy()
        message = MagicMock()
        message.content = "<think>This is my reasoning[/think]And this is the answer"

        result = strategy.extract_from_message(message)
        assert result is not None
        assert result["reasoning"] == "This is my reasoning"
        assert result["content"] == "And this is the answer"

    def test_extract_from_message_thinking_tag(self):
        """测试提取 <thinking> 标签"""
        strategy = ThinkTagStrategy()
        message = MagicMock()
        message.content = "<thinking>This is my reasoning</thinking>And this is the answer"

        result = strategy.extract_from_message(message)
        assert result is not None
        assert result["reasoning"] == "This is my reasoning"
        assert result["content"] == "And this is the answer"

    def test_extract_from_message_multiple_blocks(self):
        """测试提取多个 think 块"""
        strategy = ThinkTagStrategy()
        message = MagicMock()
        message.content = "<think>First thought</think>Hi <think>Second thought</think>There"

        result = strategy.extract_from_message(message)
        assert result is not None
        assert result["reasoning"] == "First thought\n\nSecond thought"
        assert result["content"] == "Hi There"

    def test_extract_from_message_no_tags(self):
        """测试没有 think 标签时返回 None"""
        strategy = ThinkTagStrategy()
        message = MagicMock()
        message.content = "Just regular content"

        result = strategy.extract_from_message(message)
        assert result is None

    def test_extract_from_delta_single_chunk(self):
        """测试单 chunk delta 提取（标准 </think> 格式）"""
        strategy = ThinkTagStrategy()
        delta = MagicMock()
        delta.content = "<think>reason</think>answer"

        result = strategy.extract_from_delta(delta)
        assert result["reasoning"] == "reason"
        assert result["content"] == "answer"

    def test_extract_from_delta_cross_chunk_open_first(self):
        """测试跨 chunk 提取：开标签在第一个 chunk（[/think] 格式）"""
        strategy = ThinkTagStrategy()
        delta1 = MagicMock()
        delta1.content = "<think>part1"
        delta2 = MagicMock()
        delta2.content = "part2[/think]answer"

        result1 = strategy.extract_from_delta(delta1)
        assert result1["reasoning"] == "part1"
        assert result1["content"] == ""
        assert strategy._in_thinking is True

        result2 = strategy.extract_from_delta(delta2)
        assert result2["reasoning"] == "part2"
        assert result2["content"] == "answer"
        assert strategy._in_thinking is False

    def test_extract_from_delta_cross_chunk_only_open(self):
        """测试跨 chunk 提取：只有开标签，没有闭标签"""
        strategy = ThinkTagStrategy()
        delta1 = MagicMock()
        delta1.content = "<think>reasoning starts"
        delta2 = MagicMock()
        delta2.content = " and continues"

        result1 = strategy.extract_from_delta(delta1)
        assert result1["reasoning"] == "reasoning starts"
        assert result1["content"] == ""
        assert strategy._in_thinking is True

        result2 = strategy.extract_from_delta(delta2)
        assert result2["reasoning"] == " and continues"
        assert result2["content"] == ""
        assert strategy._in_thinking is True

    def test_extract_from_delta_orphan_close_tag(self):
        """测试孤儿闭标签处理：策略层不处理，由上层 extractor 处理"""
        strategy = ThinkTagStrategy()
        delta = MagicMock()
        delta.content = "</think>answer"

        result = strategy.extract_from_delta(delta)
        # 策略层直接返回原内容，上层会调用 _strip_think_tags 清理
        assert result["content"] == "</think>answer"

    def test_extract_from_delta_reset(self):
        """测试状态重置"""
        strategy = ThinkTagStrategy()
        strategy._in_thinking = True
        strategy._open_tag = "<think>"
        strategy._close_tag = "</think>"

        strategy.reset()
        assert strategy._in_thinking is False
        assert strategy._open_tag == ""
        assert strategy._close_tag == ""


class TestDirectFieldStrategy:
    """DirectFieldStrategy 策略测试"""

    def test_extract_reasoning_content_field(self):
        """测试从 reasoning_content 字段提取"""
        strategy = DirectFieldStrategy()
        obj = MagicMock()
        obj.reasoning_content = "This is the reasoning"

        result = strategy._check(obj)
        assert result is not None
        assert result["reasoning"] == "This is the reasoning"

    def test_extract_reasoning_field(self):
        """测试从 reasoning 字段提取"""
        strategy = DirectFieldStrategy()
        obj = MagicMock()
        obj.reasoning = "This is the reasoning"

        result = strategy._check(obj)
        assert result is not None
        assert result["reasoning"] == "This is the reasoning"

    def test_extract_no_fields(self):
        """测试没有相关字段时返回 None"""
        strategy = DirectFieldStrategy()
        obj = MagicMock()

        result = strategy._check(obj)
        assert result is None


class TestModelExtraStrategy:
    """ModelExtraStrategy 策略测试"""

    def test_extract_from_model_extra_reasoning_content(self):
        """测试从 model_extra 提取 reasoning_content"""
        strategy = ModelExtraStrategy()
        obj = MagicMock()
        obj.model_extra = {"reasoning_content": "This is the reasoning"}

        result = strategy._extract_from(obj)
        assert result is not None
        assert result["reasoning"] == "This is the reasoning"

    def test_extract_from_model_extra_reasoning(self):
        """测试从 model_extra 提取 reasoning"""
        strategy = ModelExtraStrategy()
        obj = MagicMock()
        obj.model_extra = {"reasoning": "This is the reasoning"}

        result = strategy._extract_from(obj)
        assert result is not None
        assert result["reasoning"] == "This is the reasoning"

    def test_extract_no_model_extra(self):
        """测试没有 model_extra 时返回 None"""
        strategy = ModelExtraStrategy()
        obj = MagicMock()
        obj.model_extra = None

        result = strategy._extract_from(obj)
        assert result is None

    def test_extract_model_extra_no_reasoning(self):
        """测试 model_extra 中没有相关字段时返回 None"""
        strategy = ModelExtraStrategy()
        obj = MagicMock()
        obj.model_extra = {"other_field": "value"}

        result = strategy._extract_from(obj)
        assert result is None


class TestThinkingExtractor:
    """ThinkingExtractor 集成测试"""

    def test_extract_from_message_priority_order(self):
        """测试策略优先级：DirectField > ModelExtra > ThinkTag"""
        extractor = ThinkingExtractor()
        message = MagicMock()
        # 同时包含所有类型的思考内容
        message.reasoning_content = "from direct field"
        message.model_extra = {"reasoning": "from model extra"}
        message.content = "<think>from tags</think>answer"

        result = extractor.extract_from_message(message)
        # 应该优先用 DirectField 的结果
        assert result["reasoning"] == "from direct field"

    def test_extract_from_delta_fallback_to_tag_strategy(self):
        """测试没有字段时 fallback 到标签策略（标准 </think> 格式）"""
        extractor = ThinkingExtractor()
        delta = MagicMock()
        delta.content = "<think>reason</think>answer"

        result = extractor.extract_from_delta(delta)
        assert result["reasoning"] == "reason"
        assert result["content"] == "answer"

    def test_extractor_reset_calls_all_strategies(self):
        """测试 reset 调用所有策略的 reset 方法"""
        extractor = ThinkingExtractor()
        mock_strategy = MagicMock(spec=ThinkTagStrategy)
        extractor._strategies = [mock_strategy]

        extractor.reset()
        mock_strategy.reset.assert_called_once()


class TestUsageExtraction:
    """Token 用量提取测试"""

    def test_extract_usage_basic(self):
        """测试基础用量提取"""
        response = MagicMock()
        response.usage = MagicMock()
        response.usage.prompt_tokens = 100
        response.usage.completion_tokens = 200
        response.usage.total_tokens = 300

        usage = _extract_usage(response)
        assert usage["prompt_tokens"] == 100
        assert usage["completion_tokens"] == 200
        assert usage["total_tokens"] == 300

    def test_extract_usage_none_usage(self):
        """测试 usage 为 None 时返回零值"""
        response = MagicMock()
        response.usage = None

        usage = _extract_usage(response)
        assert usage["prompt_tokens"] == 0
        assert usage["completion_tokens"] == 0
        assert usage["total_tokens"] == 0

    def test_extract_usage_anthropic_cache(self):
        """测试 Anthropic 缓存用量提取"""
        response = MagicMock()
        response.usage = MagicMock()
        response.usage.prompt_tokens = 100
        response.usage.completion_tokens = 200
        response.usage.total_tokens = 300
        response.usage.cache_read_input_tokens = 50
        response.usage.cache_creation_input_tokens = 25

        usage = _extract_usage(response)
        assert usage["cache_read_tokens"] == 50
        assert usage["cache_write_tokens"] == 25

    def test_extract_usage_openai_cache(self):
        """测试 OpenAI 缓存用量提取"""
        response = MagicMock()
        response.usage = MagicMock()
        response.usage.prompt_tokens = 100
        response.usage.completion_tokens = 200
        response.usage.total_tokens = 300
        response.usage.prompt_tokens_details = MagicMock()
        response.usage.prompt_tokens_details.cached_tokens = 75

        usage = _extract_usage(response)
        assert usage["cached_tokens"] == 75
