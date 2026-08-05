"""MiniMax plugin - registers a MiniMax-specific ModelProvider.

MiniMax 在推理过程中可能字面写出闭标签（如讨论 think 格式时输出 ``</think>``
/ ``[/think]``）。核心 ThinkTagStrategy 用 find-first 匹配，会把 reasoning 中
第一个字面闭标签误当成 think 块结束，导致 reasoning 中间被截断、剩余部分错归
为 content。

MiniMax 语义下 think 块只有一个：reasoning 中较早出现的闭标签是字面文本，最后
一个闭标签才是真正结束。本 provider 用 find-last 重新提取（非流式 ``_parse_response``
+ 流式 ``chat_stream`` 流末 reconcile），覆盖核心的 find-first。其他 provider 不受
影响，仍用 OpenAICompatibleProvider。
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from merco.core.llm.openai_provider import OpenAICompatibleProvider
from merco.core.llm.thinking import THINK_TAG_PAIRS, make_thinking_extractor
from merco.plugins.base import Plugin

if TYPE_CHECKING:
    from merco.core.llm.base import ModelProviderInfo
    from merco.plugins.base import PluginContext

logger = logging.getLogger("merco.plugins.minimax")


# MiniMax models whose responses may embed reply text inside `` blocks.
_MINIMAX_MODEL_PREFIXES: tuple[str, ...] = (
    "MiniMax-",
    "abab",
)


def _is_minimax_model(model: str) -> bool:
    """Return True if the configured model name is a MiniMax model."""
    name = (model or "").lower()
    return any(name.startswith(p.lower()) for p in _MINIMAX_MODEL_PREFIXES)


class MiniMaxProvider(OpenAICompatibleProvider):
    """OpenAI-compatible transport with MiniMax think-tag extraction fix.

    MiniMax 在推理过程中可能字面写出闭标签（如讨论 think 格式时输出
    ``</think>`` / ``[/think]``）。核心 ThinkTagStrategy 用 find-first 匹配，
    会把 reasoning 中第一个字面闭标签误当成 think 块结束，导致 reasoning 在
    中间被截断、剩余部分被错归为 content。

    MiniMax 语义：think 块只有一个，reasoning 中较早出现的闭标签都是字面文本，
    最后一个闭标签才是真正的结束。故本 provider 用 find-last 重新提取：

    - 非流式 ``_parse_response``：核心提取后，用 find-last 对完整原文重新切分，
      覆盖 reasoning / content。
    - 流式 ``chat_stream``：逐 chunk 仍走核心 find-first（供实时显示），流结束后
      用 find-last 对累积原文重新切分，发一个 ``_reconcile`` chunk 覆盖累积结果
      （字面闭标签与真闭标签往往落在不同 chunk，per-chunk find-first 处理不了）。
    """

    def _parse_response(self, response) -> dict:
        result = super()._parse_response(response)
        if not response.choices:
            return result
        original = response.choices[0].message.content or ""
        reasoning, content = _split_think_blocks(original)
        # 命中 think 块（有 reasoning 或原文含闭标签）时，用 find-last 覆盖核心 find-first
        if reasoning or any(ct in original for _ot, ct in THINK_TAG_PAIRS):
            if reasoning:
                result["reasoning"] = reasoning
            result["content"] = content.strip()
        return result

    async def chat_stream(self, messages, tools=None, tool_choice="auto"):
        # 逐 chunk 走核心 find-first（实时显示）；流末用 find-last 对完整原文重新切分
        extractor = make_thinking_extractor(self.model)
        params = self._build_params(messages, tools, tool_choice, stream=True)
        stream = await self._request(params)
        raw_buf = ""
        async for chunk in stream:
            if chunk.choices:
                delta = chunk.choices[0].delta
                if delta is not None:
                    raw_buf += getattr(delta, "content", None) or ""
            if parsed := self._parse_chunk(chunk, extractor):
                yield parsed
        reasoning, content = _split_think_blocks(raw_buf)
        yield {"_reconcile": True, "reasoning": reasoning, "content": content.strip()}


def _split_think_blocks(text: str) -> tuple[str, str]:
    """用 find-last 把 ``text`` 切成 (reasoning, content)。

    语义：think 块只有一个--第一个开标签到最后一个闭标签之间是 reasoning
    （其中较早出现的闭标签视为字面文本，不作为结束），开标签之前 + 最后一个
    闭标签之后是 content。无开标签返回 ``("", text)``；有开标签无闭标签
    （流式未闭合）时开标签之后全部当 reasoning。
    """
    if not text:
        return "", ""

    # 第一个开标签（THINK_TAG_PAIRS 开标签去重保序）
    first_open = -1
    open_tag = ""
    for ot in dict.fromkeys(ot for ot, _ct in THINK_TAG_PAIRS):
        idx = text.find(ot)
        if idx != -1 and (first_open == -1 or idx < first_open):
            first_open = idx
            open_tag = ot
    if first_open == -1:
        return "", text

    # 该开标签的所有候选闭标签中，最后一个（在开标签之后）
    close_tags = [ct for (o, ct) in THINK_TAG_PAIRS if o == open_tag]
    last_close = -1
    close_tag = ""
    for ct in close_tags:
        idx = text.rfind(ct, first_open + len(open_tag))
        if idx != -1 and idx > last_close:
            last_close = idx
            close_tag = ct
    if last_close == -1:
        # 开标签已出现但闭标签未到（流式跨 chunk 未闭合）：之后全部当 reasoning
        return text[first_open + len(open_tag) :], text[:first_open]

    reasoning = text[first_open + len(open_tag) : last_close]
    content = text[:first_open] + text[last_close + len(close_tag) :]
    return reasoning, content


class MiniMaxPlugin(Plugin):
    """Registers a MiniMax-specific ModelProvider with the registry.

    Loaded via entry_points `merco.plugins` with priority 90 (after
    observability BOOT=100, before the rest). On `activate(ctx)`, it calls
    `ctx.register_model_provider` to override the built-in `minimax`
    provider with MiniMaxProvider -- which inherits OpenAICompatibleProvider
    but applies the MiniMax think-block fix.

    If `MiniMaxPlugin.activate()` raises (e.g. import error), merco falls
    back to the built-in OpenAICompatibleProvider(minimax) and the user
    will see the original behaviour; we do NOT crash the REPL.
    """

    name = "minimax"
    version = "1.0.0"
    description = "Registers MiniMaxProvider with MiniMax protocol fixes"
    priority = 90  # before agent plugins (60/50/40/30/25/20/10)

    async def activate(self, ctx: PluginContext) -> None:
        from merco.core.llm.base import ModelProviderInfo

        info: ModelProviderInfo = ModelProviderInfo(
            name="minimax",
            provider_class=MiniMaxProvider,
            display_name="MiniMax (with protocol fix)",
            base_url="https://api.minimaxi.com/v1",
            key_env="MINIMAX_API_KEY",
            key_help="https://platform.minimaxi.com/user-center/basic-information",
            default_model="MiniMax-M3",
            models=["MiniMax-M3", "MiniMax-M2.7", "MiniMax-Text-01", "abab7-chat"],
            # M2.7/M3 暂按 200K（实际约 204800，保守取整），用户可调整；Text-01 官方 1M；abab7 128K。
            context_windows={
                "MiniMax-M3": 200000,
                "MiniMax-M2.7": 200000,  # 官方文档确认 204,800 tokens，保守取 200K
                "MiniMax-Text-01": 1000000,
                "abab7-chat": 128000,
            },
            description=(
                "MiniMax provider with fix for M2.7/M3 think-block quirk "
                "(model occasionally replies inside <think> tags)"
            ),
        )
        ctx.register_model_provider(info)
        logger.debug("MiniMaxPlugin registered MiniMaxProvider")
