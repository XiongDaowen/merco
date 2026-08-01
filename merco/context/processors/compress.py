"""CompressProcessor — 替代 ContextCompressor"""

from __future__ import annotations

import logging

from merco.context.pipeline import ContextProcessor
from merco.core.context import msg_tokens

logger = logging.getLogger("merco.context.compress")


def fix_orphan_tool_results(all_messages: list[dict], kept: list[dict]) -> list[dict]:
    """补全孤立 tool 结果的前导 assistant tool_call。

    切点可能落在 assistant(tool_calls) 与 tool(result) 之间，使 tool 结果孤立，
    导致 LLM API 报 "tool result's tool id not found"。向前在全历史里找匹配的
    assistant tool_call 并补回 kept 头部。
    """
    while True:
        orphan_at = None
        for i, msg in enumerate(kept):
            if msg.get("role") != "tool":
                continue
            prev = kept[i - 1] if i > 0 else None
            if not (prev and prev.get("role") == "assistant" and prev.get("tool_calls")):
                orphan_at = i
                break
        if orphan_at is None:
            break
        try:
            orig_idx = all_messages.index(kept[orphan_at])
        except ValueError:
            break
        asst_idx = None
        for j in range(orig_idx - 1, -1, -1):
            msg = all_messages[j]
            if msg.get("role") == "assistant" and msg.get("tool_calls"):
                asst_idx = j
                break
        if asst_idx is None:
            break
        # 拉回 assistant + 它在切点前的所有 tool 结果（避免 tool_call 有声明无结果）
        to_add = [m for m in all_messages[asst_idx:orig_idx] if m not in kept]
        if not to_add:
            break
        kept[:0] = to_add
    return kept


class CompressProcessor(ContextProcessor):
    """压缩：超过阈值时摘要旧消息"""

    name = "compress"

    def __init__(self, max_tokens: int = 64000, threshold: float = 0.75):
        self.max_tokens = max_tokens
        self.threshold = threshold

    async def process(self, messages: list[dict], **kwargs) -> list[dict]:
        total = sum(msg_tokens(m) for m in messages)
        trigger = int(self.max_tokens * self.threshold)
        if total <= trigger or len(messages) <= 4:
            return messages

        strategy = kwargs.get("compress_strategy", "sliding")
        summary_fn = kwargs.get("summary_fn")

        if strategy == "sliding":
            return await self._sliding(messages, summary_fn)
        elif strategy == "truncate":
            return self._truncate(messages)
        return messages

    async def _sliding(self, messages: list[dict], summary_fn=None) -> list[dict]:
        """滑动窗口压缩 — 保留最后 2 轮原文 + 摘要旧消息"""
        tail_turns = 2

        tail_start = 0
        user_count = 0
        for i in range(len(messages) - 1, -1, -1):
            if messages[i].get("role") == "user":
                user_count += 1
                if user_count >= tail_turns:
                    tail_start = i
                    break

        body = messages[:tail_start]
        tail = messages[tail_start:]

        if not body:
            return messages

        if summary_fn:
            try:
                summary_text = await summary_fn(body)
                summary = {"role": "system", "content": summary_text}
            except Exception as e:
                logger.warning("LLM 摘要失败: %s, fallback", e)
                summary = self._build_summary(body)
        else:
            summary = self._build_summary(body)

        result = [m for m in tail if m.get("role") == "system"][:1]
        result.append(summary)
        result.extend(m for m in tail if m.get("role") != "system")

        before = sum(msg_tokens(m) for m in messages)
        after = sum(msg_tokens(m) for m in result)
        logger.debug("压缩: %d条(%dtok) → %d条(%dtok)", len(messages), before, len(result), after)
        return result

    def _truncate(self, messages: list[dict]) -> list[dict]:
        """简单截断 fallback"""
        if len(messages) <= 6:
            return messages
        kept = messages[-6:]
        return self._extend_to_chain(messages, messages[:-6], kept)

    def _extend_to_chain(self, all_messages, before, kept):
        """补全孤立 tool 消息的前导 assistant（委托 fix_orphan_tool_results）。"""
        return fix_orphan_tool_results(all_messages, kept)

    def _build_summary(self, messages: list[dict]) -> dict:
        """Fallback 摘要"""
        user_msgs = [m for m in messages if m.get("role") == "user"]
        preview = []
        for um in user_msgs[-5:]:
            c = um.get("content", "")[:60]
            if c:
                preview.append(f"• {c}")
        intro = (
            f"[压缩了 {len(messages)} 条历史消息。"
            f"最近讨论: {'; '.join(preview) if preview else '无'}。"
            f"详细历史请用 /search 查询。]"
        )
        return {"role": "system", "content": intro}
