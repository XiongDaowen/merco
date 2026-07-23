"""ThinkingExtractor + strategies + factory."""
from types import SimpleNamespace
from merco.core.llm.thinking import (
    ThinkingExtractor, make_thinking_extractor, ThinkTagStrategy,
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
    from merco.core.llm.thinking import DirectFieldStrategy
    ex = ThinkingExtractor()  # default chain includes DirectFieldStrategy
    msg = SimpleNamespace(content="answer", reasoning_content="chain of thought")
    result = ex.extract_from_message(msg)
    assert result["reasoning"] == "chain of thought"
