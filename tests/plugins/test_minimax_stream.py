"""MiniMaxProvider think-tag 提取回归测试。

回归 bug：reasoning 中字面出现闭标签（如模型讨论 think 格式时输出 ``</think>``），
核心 ThinkTagStrategy 用 find-first 会把第一个字面闭标签误当成 think 块结束，
导致 reasoning 中间被截断、剩余部分错归为 content。

MiniMax 语义：think 块只有一个，最后一个闭标签才是真正结束。本 provider 用
find-last 重新提取（非流式 ``_parse_response`` + 流式 ``chat_stream`` 流末 reconcile）。
"""

import asyncio
from types import SimpleNamespace

from merco.core.llm.thinking import make_thinking_extractor
from merco.plugins.builtin.minimax.plugin import MiniMaxProvider, _split_think_blocks


def _mkchunk(content):
    """构造一个最小可用的 OpenAI stream chunk mock。"""
    delta = SimpleNamespace(content=content, tool_calls=None)
    choice = SimpleNamespace(delta=delta, finish_reason=None)
    return SimpleNamespace(choices=[choice], usage=None)


def _provider():
    prov = MiniMaxProvider.__new__(MiniMaxProvider)
    prov.model = "MiniMax-M3"
    prov._extractor = make_thinking_extractor("MiniMax-M3")
    return prov


def _response(content):
    """构造一个最小可用的非流式 response mock。"""
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=content, role="assistant", tool_calls=None),
                finish_reason="stop",
            )
        ],
        usage=None,
    )


# ── _split_think_blocks (find-last 单元) ──────────────────────


class TestSplitThinkBlocks:
    def test_literal_close_tag_in_reasoning(self):
        """reasoning 中字面出现 </think>：最后一个闭标签才是结束。"""
        text = "<think>先想，输出 </think> 继续，好的</think>这是回复"
        reasoning, content = _split_think_blocks(text)
        assert reasoning == "先想，输出 </think> 继续，好的"
        assert content == "这是回复"

    def test_normal_single_block(self):
        """正常单 think 块：find-last == find-first。"""
        reasoning, content = _split_think_blocks("<think>推理</think>回复")
        assert reasoning == "推理"
        assert content == "回复"

    def test_alternate_close_tag(self):
        """[/think] 闭标签格式同样适用 find-last。"""
        text = "<think>推理 [/think] 继续</think>回复"
        reasoning, content = _split_think_blocks(text)
        assert reasoning == "推理 [/think] 继续"
        assert content == "回复"

    def test_no_think_block(self):
        """无 think 标签：整段当 content。"""
        reasoning, content = _split_think_blocks("只是个回复")
        assert reasoning == ""
        assert content == "只是个回复"

    def test_open_no_close(self):
        """有开标签无闭标签（流式未闭合）：之后全部当 reasoning。"""
        reasoning, content = _split_think_blocks("<think>推理中")
        assert reasoning == "推理中"
        assert content == ""

    def test_empty(self):
        assert _split_think_blocks("") == ("", "")


# ── 非流式 _parse_response ────────────────────────────────────


class TestParseResponse:
    def test_literal_tag_not_truncated(self):
        """非流式：reasoning 中字面闭标签不截断。"""
        prov = _provider()
        raw = "<think>先想，输出 </think> 继续，好的</think>这是回复"
        r = prov._parse_response(_response(raw))
        assert r["reasoning"] == "先想，输出 </think> 继续，好的"
        assert r["content"] == "这是回复"

    def test_normal_response(self):
        """非流式：正常 think 块 + 回复。"""
        prov = _provider()
        r = prov._parse_response(_response("<think>推理</think>回复"))
        assert r["reasoning"] == "推理"
        assert r["content"] == "回复"

    def test_no_think_tags(self):
        """非流式：无 think 标签，content 原样（不被 find-last 覆盖）。"""
        prov = _provider()
        r = prov._parse_response(_response("只是个回复"))
        assert r["content"] == "只是个回复"
        assert r["reasoning"] == ""


# ── 流式 chat_stream reconcile ────────────────────────────────


class TestStreamingReconcile:
    def test_chat_stream_emits_reconcile_with_find_last(self):
        """流式：字面闭标签与真闭标签落不同 chunk，流末 _reconcile chunk 用 find-last 修正。"""
        prov = _provider()
        stream_chunks = ["<think>", "先想，输出 ", "</think>", " 继续，好的", "</think>", "这是回复"]

        async def fake_request(params):
            async def gen():
                for c in stream_chunks:
                    yield _mkchunk(c)

            return gen()

        prov._request = fake_request
        prov._build_params = lambda messages, tools, tool_choice, stream=False: {}

        async def collect():
            out = []
            async for ch in prov.chat_stream([], None, "auto"):
                out.append(ch)
            return out

        chunks = asyncio.run(collect())
        # 最后一项是 _reconcile chunk
        reconcile = chunks[-1]
        assert reconcile.get("_reconcile") is True
        assert reconcile["reasoning"] == "先想，输出 </think> 继续，好的"
        assert reconcile["content"] == "这是回复"
        # 前面的 chunk 是 per-chunk 解析（含被误切的 content，待 reconcile 覆盖）
        assert any(c.get("content") for c in chunks[:-1])

    def test_chat_stream_reconcile_normal_block(self):
        """流式：正常单 think 块，reconcile 结果与 per-chunk 一致。"""
        prov = _provider()
        stream_chunks = ["<think>", "推理", "</think>", "回复"]

        async def fake_request(params):
            async def gen():
                for c in stream_chunks:
                    yield _mkchunk(c)

            return gen()

        prov._request = fake_request
        prov._build_params = lambda messages, tools, tool_choice, stream=False: {}

        async def collect():
            out = []
            async for ch in prov.chat_stream([], None, "auto"):
                out.append(ch)
            return out

        chunks = asyncio.run(collect())
        reconcile = chunks[-1]
        assert reconcile.get("_reconcile") is True
        assert reconcile["reasoning"] == "推理"
        assert reconcile["content"] == "回复"
