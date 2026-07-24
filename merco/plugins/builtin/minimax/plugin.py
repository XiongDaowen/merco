"""MiniMax plugin - registers a MiniMax-specific ModelProvider.

MiniMax protocol quirk: the model occasionally emits the user-visible reply
*inside* the `` block (e.g. ``hello你好！``),
before the closing tag. The default ThinkTagStrategy extracts the entire
block content as `reasoning`, leaving `content` empty -- which then triggers
a spurious EmptyResponsePipeline callback in the agent loop.

This plugin wraps OpenAICompatibleProvider in MiniMaxProvider, which re-runs
the think-tag extraction against the *complete* `message.content` (or
assembled chunk content for streaming) so the user-visible text outside the
last `` tag is restored to `content`.

The fix is scoped to model names that match MiniMax's quirks; other
providers are unaffected (they keep using OpenAICompatibleProvider).
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from merco.core.llm.openai_provider import OpenAICompatibleProvider
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
    """OpenAI-compatible transport with MiniMax protocol fixes.

    Inherits *all* behaviour from OpenAICompatibleProvider (timeouts,
    retries, error translation, usage extraction, tool_calls
    normalisation, streaming chunk assembly) and only overrides the two
    response-parsing methods that suffer from MiniMax's `` quirk.
    """

    def _parse_response(self, response) -> dict:
        result = super()._parse_response(response)
        # MiniMax fix: if thinking extraction emptied `content` because the
        # model replied inside ``, recover the post-think text from
        # the *original* message.content and prepend it.
        if (
            not result.get("content")
            and not result.get("tool_calls")
            and not result.get("reasoning", "").rstrip().endswith("")
        ):
            # reasoning ended cleanly on a closing tag -- the model
            # likely put everything in ``; nothing to recover.
            return result
        if not result.get("content") and response.choices:
            original = response.choices[0].message.content or ""
            recovered = _split_think_blocks(original)[1]
            if recovered:
                result["content"] = recovered
                logger.debug(
                    "MiniMax fix: recovered %d chars of content from think-block boundary",
                    len(recovered),
                )
        return result

    def _parse_chunk(self, chunk, extractor=None):
        result = super()._parse_chunk(chunk, extractor)
        if not result:
            return result
        # MiniMax streaming fix: per-chunk the state machine may swallow
        # content that arrived before `` closed. When the stream ends
        # we have the full assembled chunk text in `reasoning`; the last
        # segment after the closing tag is the real reply.
        if not result.get("content") and result.get("reasoning"):
            recovered = _split_think_blocks(result["reasoning"])[1]
            if recovered:
                result["content"] = recovered
                result["reasoning"] = _split_think_blocks(result["reasoning"])[0]
        return result


def _split_think_blocks(text: str) -> tuple[str, str]:
    """Split ``text`` into (thinking, post-thinking reply).

    Tries each (open, close) tag pair in THINK_TAG_PAIRS, in order, scanning
    for the LAST matching pair. The reasoning segment is everything from
    the matched open tag to the matched close tag (inclusive); the reply
    segment is everything after the close tag, stripped.

    Returns ``("", text)`` if no think block is found -- meaning the entire
    text is the user-visible reply.
    """
    from merco.core.llm.thinking import THINK_TAG_PAIRS

    if not text:
        return "", ""

    best_open = -1
    best_close = -1

    # Find the LAST matching (open, close) pair by scanning all open positions
    # in reverse and looking for the corresponding close after each.
    for ot, ct in THINK_TAG_PAIRS:
        # Walk every occurrence of `ot` (from last to first); for each, the
        # matching close is the first `ct` after that position.
        start = len(text)
        while True:
            start = text.rfind(ot, 0, start)
            if start < 0:
                break
            end = text.find(ct, start + len(ot))
            if end < 0:
                # This open has no matching close; skip and look for an earlier open.
                continue
            # Pick this pair if it's later than what we have so far.
            if end > best_close:
                best_open = start
                best_close = end
                # Tag tracker only used for readability (same as best_close_tag below).
                best_open_tag = ot  # noqa: F841
                best_close_tag = ct
            # Continue searching earlier opens for the same tag pair.
            # (don't break — we want the LAST matching pair, so keep going
            #  backwards from this start)

    if best_open < 0:
        # No matching think block at all.
        return "", text

    reasoning = text[best_open : best_close + len(best_close_tag)]
    after = text[best_close + len(best_close_tag) :]
    return reasoning, after.strip()


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
            description=(
                "MiniMax provider with fix for M2.7/M3 think-block quirk "
                "(model occasionally replies inside <think> tags)"
            ),
        )
        ctx.register_model_provider(info)
        logger.debug("MiniMaxPlugin registered MiniMaxProvider")
