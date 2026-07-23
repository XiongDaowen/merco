"""Context Pipeline 端到端集成测试"""
import pytest
from merco.context.pipeline import ContextPipeline
from merco.context.processors.compress import CompressProcessor
from merco.context.processors.cache_optimize import CacheOptimizeProcessor


async def test_pipeline_with_compress(test_agent):
    """Context Pipeline 压缩端到端"""
    from tests.conftest import MockModelProvider

    # Set very small max_input_tokens so compression is triggered easily
    test_agent.config.max_input_tokens = 20000
    test_agent.config.compression_threshold = 0.75
    test_agent.context.max_tokens = 20000

    # Replace pipeline with small-token CompressProcessor to match
    from merco.context.pipeline import ContextPipeline
    test_agent.context_pipeline = ContextPipeline()
    test_agent.context_pipeline.use(CacheOptimizeProcessor())
    test_agent.context_pipeline.use(CompressProcessor(
        max_tokens=20000,
        threshold=0.75,
    ))

    # Provide enough mock LLM responses for 4 turns
    test_agent.provider = MockModelProvider([
        {"content": "reply0"},
        {"content": "reply1"},
        {"content": "reply2"},
        {"content": "reply3"},
    ])

    # Run 4 turns with large messages to exceed token threshold
    for i in range(4):
        await test_agent.run("x" * 22000)

    # After compression, context should have fewer messages than
    # 4 user + 4 assistant = 8
    assert len(test_agent.context.messages) < 8


async def test_cache_optimize_processor():
    """CacheOptimizeProcessor 重排序"""
    proc = CacheOptimizeProcessor()
    msgs = [
        {"role": "user", "content": "hi"},
        {"role": "system", "content": "system prompt"},
        {"role": "assistant", "content": "hello"},
    ]
    result = await proc.process(msgs)
    assert result[0]["role"] == "system"
    assert result[1]["role"] == "user"
    assert result[2]["role"] == "assistant"
