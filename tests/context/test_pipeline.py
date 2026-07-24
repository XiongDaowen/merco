"""ContextPipeline 单测"""
import pytest

from merco.context.pipeline import ContextPipeline, ContextProcessor


class AppendProcessor(ContextProcessor):
    """测试用处理器：追加一条消息"""
    name = "append"

    def __init__(self, content: str):
        self.content = content

    async def process(self, messages, **kwargs):
        return messages + [{"role": "system", "content": self.content}]


class DoubleProcessor(ContextProcessor):
    """测试用处理器：复制所有消息"""
    name = "double"

    async def process(self, messages, **kwargs):
        return messages + messages


@pytest.fixture
def pipeline():
    return ContextPipeline()


async def test_pipeline_empty(pipeline):
    """空管线返回原消息"""
    msgs = [{"role": "user", "content": "hi"}]
    result = await pipeline.run(msgs)
    assert result == msgs


async def test_pipeline_single_processor(pipeline):
    """单处理器"""
    pipeline.use(AppendProcessor("added"))
    msgs = [{"role": "user", "content": "hi"}]
    result = await pipeline.run(msgs)
    assert len(result) == 2
    assert result[1]["content"] == "added"


async def test_pipeline_order(pipeline):
    """处理器按注册顺序执行"""
    pipeline.use(AppendProcessor("first"))
    pipeline.use(AppendProcessor("second"))
    msgs = [{"role": "user", "content": "hi"}]
    result = await pipeline.run(msgs)
    assert len(result) == 3
    assert result[1]["content"] == "first"
    assert result[2]["content"] == "second"


async def test_pipeline_chaining(pipeline):
    """处理器链式执行：第一个的输出是第二个的输入"""
    pipeline.use(AppendProcessor("added"))
    pipeline.use(DoubleProcessor())
    msgs = [{"role": "user", "content": "hi"}]
    result = await pipeline.run(msgs)
    assert len(result) == 4  # 2 from first + 2 from double
