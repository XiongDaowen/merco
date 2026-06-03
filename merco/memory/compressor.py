"""上下文压缩器 — token 感知 + 不断链 + LLM 语义摘要"""

import logging

logger = logging.getLogger("merco.compressor")
from merco.core.context import msg_tokens, estimate_tokens


class ContextCompressor:
    """压缩对话历史，保证 tool_calls 链完整 + token 阈值"""

    def __init__(self, max_input_tokens: int = 64000, threshold: float = 0.75):
        self.max_input_tokens = max_input_tokens
        self.threshold = threshold

    async def compress(self, messages: list[dict], strategy: str = "sliding",
                       summary_fn=None) -> list[dict]:
        total = self._total_tokens(messages)
        trigger = int(self.max_input_tokens * self.threshold)
        if total <= trigger or len(messages) <= 4:
            return messages

        if strategy == "sliding":
            return await self._sliding(messages, summary_fn)
        elif strategy == "truncate":
            return self._truncate(messages)
        return messages

    def _total_tokens(self, messages: list[dict]) -> int:
        return sum(msg_tokens(m) for m in messages)

    async def _sliding(self, messages: list[dict], summary_fn=None) -> list[dict]:
        """滑动窗口压缩 — 保留最后 2 轮原文 + 摘要旧消息"""
        TAIL_TURNS = 2  # 保留最近 N 轮原文不压缩

        # —— 1. 找出最后 N 条 user 消息，保留它们的完整 tool 链 ——
        tail_start = 0
        user_count = 0
        for i in range(len(messages) - 1, -1, -1):
            if messages[i].get("role") == "user":
                user_count += 1
                if user_count >= TAIL_TURNS:
                    tail_start = i
                    break

        body = messages[:tail_start]  # 旧消息 → 压缩
        tail = messages[tail_start:]  # 最近 N 轮 → 保留

        if not body:
            return messages  # 不够 TAIL_TURNS 轮，不压缩

        # —— 2. LLM 摘要 body ——
        if summary_fn:
            try:
                summary_text = await summary_fn(body)
                summary = {"role": "system", "content": summary_text}
            except Exception as e:
                logger.warning("LLM 摘要失败: %s, fallback", e)
                summary = self._build_summary(body)
        else:
            summary = self._build_summary(body)

        # —— 3. 组装: system + 摘要 + 尾巴 ——
        result = [m for m in tail if m.get("role") == "system"][:1]  # 保留最高层 system
        result.append(summary)
        result.extend(m for m in tail if m.get("role") != "system")

        before = self._total_tokens(messages)
        after = self._total_tokens(result)
        logger.debug("压缩: %d条(%dtok) → %d条(%dtok) — 保留 %d 轮",
                     len(messages), before, len(result), after, TAIL_TURNS)
        return result

    def _truncate(self, messages: list[dict]) -> list[dict]:
        """简单截断 fallback"""
        if len(messages) <= 6:
            return messages
        kept = messages[-6:]
        return self._extend_to_chain(messages, messages[:-6], kept)

    def _extend_to_chain(self, all_messages, before, kept):
        """从 before 区域往回找，补全 kept 中孤立 tool 消息的前导 assistant"""
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
            found = None
            for j in range(orig_idx - 1, -1, -1):
                msg = all_messages[j]
                if msg.get("role") == "assistant" and msg.get("tool_calls"):
                    found = msg
                    break
            if found is None or found in kept:
                break
            kept.insert(0, found)
        return kept

    def _build_summary(self, messages: list[dict]) -> dict:
        """Fallback 摘要 — 保留最近几条用户消息的关键内容"""
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
