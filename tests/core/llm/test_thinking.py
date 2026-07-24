"""ThinkingExtractor + strategies + factory."""
from types import SimpleNamespace
from unittest.mock import MagicMock

from merco.core.llm.thinking import (
    DirectFieldStrategy,
    ModelExtraStrategy,
    ThinkingExtractor,
    ThinkTagStrategy,
    _clean_content,
    _strip_think_tags,
    make_thinking_extractor,
)


def test_factory_picks_think_tag_for_deepseek():
    ex = make_thinking_extractor("deepseek-reasoner")
    assert any(isinstance(s, ThinkTagStrategy) for s in ex._strategies)


def test_factory_default_has_all_three_strategies():
    ex = make_thinking_extractor("gpt-4o")
    assert len(ex._strategies) == 3


def test_extract_think_tag_from_message():
    ex = make_thinking_extractor("deepseek-chat")
    msg = SimpleNamespace(content="<think>hidden reasoning</think>visible answer")
    result = ex.extract_from_message(msg)
    assert result["reasoning"] == "hidden reasoning"
    assert result["content"] == "visible answer"


def test_extract_direct_field_reasoning():
    ex = ThinkingExtractor()  # default chain includes DirectFieldStrategy
    msg = SimpleNamespace(content="answer", reasoning_content="chain of thought")
    result = ex.extract_from_message(msg)
    assert result["reasoning"] == "chain of thought"


# ── _strip_think_tags / _clean_content unit behavior ──

class TestThinkTagHandling:
    """Think 标签底层清理：_strip_think_tags（chunk 安全，不动空白）与 _clean_content（终态 strip）。"""

    def test_strip_think_tags_standard(self):
        """标准 <think>...</think> 块清理。"""
        assert _strip_think_tags("<think>This is thinking</think>Hello World") == "Hello World"

    def test_strip_think_tags_alternate(self):
        """[/think] 闭标签格式清理。"""
        assert _strip_think_tags("<think>This is thinking[/think]Hello World") == "Hello World"

    def test_strip_think_tags_thinking(self):
        """<thinking>...</thinking> 标签清理。"""
        assert _strip_think_tags("<thinking>This is thinking</thinking>Hello World") == "Hello World"

    def test_strip_think_tags_multiple(self):
        """多个 think 块全部清理。"""
        assert _strip_think_tags("<think>1</think>Hi <think>2</think>There") == "Hi There"

    def test_strip_think_tags_case_insensitive(self):
        """大小写不敏感。"""
        assert _strip_think_tags("<THINK>This is thinking</THINK>Hello World") == "Hello World"

    def test_strip_think_tags_orphan_open(self):
        """孤儿开标签：只移除标签，保留其后内容。"""
        assert _strip_think_tags("<think>This is thinkingHello World") == "This is thinkingHello World"

    def test_strip_think_tags_orphan_close(self):
        """孤儿闭标签：只移除标签，保留其余内容。"""
        assert _strip_think_tags("This is thinking</think>Hello World") == "This is thinkingHello World"

    def test_clean_content(self):
        """完整内容清理：去 think 标签 + 去前后空白。"""
        assert _clean_content("  <think>This is thinking</think>  Hello World  ") == "Hello World"


def test_strip_think_tags_preserves_internal_whitespace():
    """回归测试：_strip_think_tags 在流式场景下不应破坏词边界。
    旧实现末尾 .strip() 会去掉每 chunk 的首尾空白，拼接后空格消失。
    """
    chunks = ["hello ", "world", " how ", "are you"]
    buf = ""
    for c in chunks:
        buf += _strip_think_tags(c)
    assert buf == "hello world how are you", f"spaces lost: {buf!r}"

    # think 块（标准闭合）正常剥离
    assert _strip_think_tags("<think>hi</think>hello world") == "hello world"
    assert _strip_think_tags("a<think>b</think>c") == "ac"
    # 多行 think 块也能剥离（DOTALL 已加）
    assert _strip_think_tags("<think>line1\nline2</think>after") == "after"
    # 前后空白保留（chunk 安全）
    assert _strip_think_tags("  hello  ") == "  hello  "


def test_clean_content_strips_think_tags_and_outer_whitespace():
    """_clean_content 是非流式终态处理：去标签 + strip 前后空白。"""
    assert _clean_content("  hello world  ") == "hello world"
    assert _clean_content("<think>thinking</think>real content") == "real content"
    assert _clean_content("<think>t1</think> middle <think>t2</think>") == "middle"


# ── ThinkTagStrategy (incl. cross-chunk delta) ──

class TestThinkTagStrategy:
    """ThinkTagStrategy 策略测试，含跨 chunk 状态机。"""

    def test_extract_from_message_standard(self):
        """从完整消息中提取标准 think 标签。"""
        strategy = ThinkTagStrategy()
        message = SimpleNamespace(
            content="<think>This is my reasoning</think>And this is the answer"
        )
        result = strategy.extract_from_message(message)
        assert result is not None
        assert result["reasoning"] == "This is my reasoning"
        assert result["content"] == "And this is the answer"

    def test_extract_from_message_alternate_close(self):
        """提取 [/think] 格式的标签。"""
        strategy = ThinkTagStrategy()
        message = SimpleNamespace(
            content="<think>This is my reasoning[/think]And this is the answer"
        )
        result = strategy.extract_from_message(message)
        assert result is not None
        assert result["reasoning"] == "This is my reasoning"
        assert result["content"] == "And this is the answer"

    def test_extract_from_message_thinking_tag(self):
        """提取 <thinking> 标签。"""
        strategy = ThinkTagStrategy()
        message = SimpleNamespace(
            content="<thinking>This is my reasoning</thinking>And this is the answer"
        )
        result = strategy.extract_from_message(message)
        assert result is not None
        assert result["reasoning"] == "This is my reasoning"
        assert result["content"] == "And this is the answer"

    def test_extract_from_message_multiple_blocks(self):
        """提取多个 think 块（reasoning 用 \\n\\n 拼接，content 去标签后 strip）。"""
        strategy = ThinkTagStrategy()
        message = SimpleNamespace(
            content="<think>First thought</think>Hi <think>Second thought</think>There"
        )
        result = strategy.extract_from_message(message)
        assert result is not None
        assert result["reasoning"] == "First thought\n\nSecond thought"
        assert result["content"] == "Hi There"

    def test_extract_from_message_no_tags(self):
        """没有 think 标签时返回 None。"""
        strategy = ThinkTagStrategy()
        message = SimpleNamespace(content="Just regular content")
        result = strategy.extract_from_message(message)
        assert result is None

    def test_extract_from_delta_single_chunk(self):
        """单 chunk delta 提取（标准 </think> 格式）。"""
        strategy = ThinkTagStrategy()
        delta = SimpleNamespace(content="<think>reason</think>answer")
        result = strategy.extract_from_delta(delta)
        assert result["reasoning"] == "reason"
        assert result["content"] == "answer"

    def test_extract_from_delta_cross_chunk_open_first(self):
        """跨 chunk 提取：开标签在第一个 chunk（[/think] 闭标签在第二个 chunk）。"""
        strategy = ThinkTagStrategy()
        delta1 = SimpleNamespace(content="<think>part1")
        delta2 = SimpleNamespace(content="part2[/think]answer")

        result1 = strategy.extract_from_delta(delta1)
        assert result1["reasoning"] == "part1"
        assert result1["content"] == ""
        assert strategy._in_thinking is True

        result2 = strategy.extract_from_delta(delta2)
        assert result2["reasoning"] == "part2"
        assert result2["content"] == "answer"
        assert strategy._in_thinking is False

    def test_extract_from_delta_cross_chunk_only_open(self):
        """跨 chunk 提取：只有开标签，后续 chunk 仍处于 thinking 状态。"""
        strategy = ThinkTagStrategy()
        delta1 = SimpleNamespace(content="<think>reasoning starts")
        delta2 = SimpleNamespace(content=" and continues")

        result1 = strategy.extract_from_delta(delta1)
        assert result1["reasoning"] == "reasoning starts"
        assert result1["content"] == ""
        assert strategy._in_thinking is True

        result2 = strategy.extract_from_delta(delta2)
        assert result2["reasoning"] == " and continues"
        assert result2["content"] == ""
        assert strategy._in_thinking is True

    def test_extract_from_delta_orphan_close_tag(self):
        """孤儿闭标签：策略层不处理，原样返回，由上层 extractor 调 _strip_think_tags 清理。"""
        strategy = ThinkTagStrategy()
        delta = SimpleNamespace(content="</think>answer")
        result = strategy.extract_from_delta(delta)
        assert result["content"] == "</think>answer"

    def test_extract_from_delta_reset(self):
        """状态重置：_in_thinking / _open_tag / _close_tag 全部清空。"""
        strategy = ThinkTagStrategy()
        strategy._in_thinking = True
        strategy._open_tag = "<think>"
        strategy._close_tag = "</think>"

        strategy.reset()
        assert strategy._in_thinking is False
        assert strategy._open_tag == ""
        assert strategy._close_tag == ""


# ── DirectFieldStrategy ─────────────────────

class TestDirectFieldStrategy:
    """DirectFieldStrategy：从顶层 reasoning_content / reasoning 字段提取。"""

    def test_extract_reasoning_content_field(self):
        """从 reasoning_content 字段提取。"""
        strategy = DirectFieldStrategy()
        obj = SimpleNamespace(reasoning_content="This is the reasoning")
        result = strategy._check(obj)
        assert result is not None
        assert result["reasoning"] == "This is the reasoning"

    def test_extract_reasoning_field(self):
        """从 reasoning 字段提取。"""
        strategy = DirectFieldStrategy()
        obj = SimpleNamespace(reasoning="This is the reasoning")
        result = strategy._check(obj)
        assert result is not None
        assert result["reasoning"] == "This is the reasoning"

    def test_extract_no_fields(self):
        """没有相关字段时返回 None。"""
        strategy = DirectFieldStrategy()
        obj = SimpleNamespace()
        result = strategy._check(obj)
        assert result is None


# ── ModelExtraStrategy ──────────────────────

class TestModelExtraStrategy:
    """ModelExtraStrategy：从 model_extra 字典提取 reasoning_content / reasoning。"""

    def test_extract_from_model_extra_reasoning_content(self):
        """从 model_extra 提取 reasoning_content。"""
        strategy = ModelExtraStrategy()
        obj = SimpleNamespace(model_extra={"reasoning_content": "This is the reasoning"})
        result = strategy._extract_from(obj)
        assert result is not None
        assert result["reasoning"] == "This is the reasoning"

    def test_extract_from_model_extra_reasoning(self):
        """从 model_extra 提取 reasoning。"""
        strategy = ModelExtraStrategy()
        obj = SimpleNamespace(model_extra={"reasoning": "This is the reasoning"})
        result = strategy._extract_from(obj)
        assert result is not None
        assert result["reasoning"] == "This is the reasoning"

    def test_extract_no_model_extra(self):
        """没有 model_extra（None）时返回 None。"""
        strategy = ModelExtraStrategy()
        obj = SimpleNamespace(model_extra=None)
        result = strategy._extract_from(obj)
        assert result is None

    def test_extract_model_extra_no_reasoning(self):
        """model_extra 中没有相关字段时返回 None。"""
        strategy = ModelExtraStrategy()
        obj = SimpleNamespace(model_extra={"other_field": "value"})
        result = strategy._extract_from(obj)
        assert result is None


# ── ThinkingExtractor integration ───────────

class TestThinkingExtractor:
    """ThinkingExtractor 集成测试：优先级 / fallback / reset 委托。"""

    def test_extract_from_message_priority_order(self):
        """策略优先级：DirectField > ModelExtra > ThinkTag。"""
        extractor = ThinkingExtractor()
        message = SimpleNamespace(
            reasoning_content="from direct field",
            model_extra={"reasoning": "from model extra"},
            content="<think>from tags</think>answer",
        )
        result = extractor.extract_from_message(message)
        assert result["reasoning"] == "from direct field"

    def test_extract_from_delta_fallback_to_tag_strategy(self):
        """没有直接字段时 fallback 到标签策略（标准 </think> 格式）。"""
        extractor = ThinkingExtractor()
        delta = SimpleNamespace(content="<think>reason</think>answer")
        result = extractor.extract_from_delta(delta)
        assert result["reasoning"] == "reason"
        assert result["content"] == "answer"

    def test_extractor_reset_calls_all_strategies(self):
        """reset 调用所有策略的 reset 方法。"""
        extractor = ThinkingExtractor()
        mock_strategy = MagicMock(spec=ThinkTagStrategy)
        extractor._strategies = [mock_strategy]
        extractor.reset()
        mock_strategy.reset.assert_called_once()
