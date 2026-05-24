"""上下文压缩器 — token 感知 + 不断链 + LLM 语义摘要"""

import logging

logger = logging.getLogger("openmercury.compressor")
from openmercury.core.context import msg_tokens, estimate_tokens


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
        """滑动窗口压缩"""

        # —— 1. 分类 ——
        # 最后一条 user 的索引
        last_user_idx = None
        for i, msg in enumerate(messages):
            if msg.get("role") == "user":
                last_user_idx = i

        # 从尾往前扫：当前 tool 链 + 最终回复
        tail = []
        tail_ids = set()
        in_chain = False  # 是否在 tool_calls → tool 链中
        for msg in reversed(messages):
            role = msg.get("role", "")
            rid = id(msg)

            if role == "assistant" and not msg.get("tool_calls") and not in_chain:
                # 纯文本回复（不含 tool_calls），且不在链中 → 最终回复
                tail.insert(0, msg)
                tail_ids.add(rid)
            elif role == "tool":
                tail.insert(0, msg)
                tail_ids.add(rid)
                in_chain = True
            elif role == "assistant" and msg.get("tool_calls"):
                if in_chain:
                    tail.insert(0, msg)
                    tail_ids.add(rid)
                else:
                    break  # 当前链结束
            else:
                break  # 遇到非链消息，停止

        # —— 2. 保留项 + 压缩项 ——
        kept = []

        for i, msg in enumerate(messages):
            role = msg.get("role", "")
            rid = id(msg)

            if role == "system":
                kept.append(msg)
            elif i == last_user_idx:
                kept.append(msg)  # 当前任务
            elif rid in tail_ids:
                pass  # 等尾部分类完统一处理
            elif role == "user":
                kept.append(msg)  # 旧 user 消息也进压缩
            elif role in ("assistant", "tool"):
                kept.append(msg)  # 旧消息进压缩
            else:
                kept.append(msg)

        # —— 3. LLM 摘要压缩项 ——
        if summary_fn and kept:
            try:
                summary_text = await summary_fn(kept)
                summary = {"role": "system", "content": summary_text}
            except Exception as e:
                logger.warning("LLM 摘要失败: %s", e)
                summary = self._build_summary(kept)
        else:
            summary = self._build_summary(kept)

        # —— 4. 组装：保留 key + 摘要 + 尾巴 ——
        result = []
        for i, msg in enumerate(messages):
            role = msg.get("role", "")
            rid = id(msg)

            if role == "system":
                result.append(msg)
            elif i == last_user_idx:
                result.append(msg)
                result.append(summary)  # 摘要插在最后一条 user 之后
            # 跳过尾巴中的消息（稍后统一加）
            elif rid in tail_ids:
                continue
            # 其他 user 消息不保留

        # 加尾巴
        result.extend(tail)

        logger.debug("压缩: %d条(%dtok) → %d条(%dtok) — LLM摘要 %d条",
                     len(messages), self._total_tokens(messages),
                     len(result), self._total_tokens(result), len(kept))
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
        """统计摘要 fallback"""
        user_msgs = sum(1 for m in messages if m.get("role") == "user")
        assistant_msgs = sum(1 for m in messages if m.get("role") == "assistant")
        tool_msgs = sum(1 for m in messages if m.get("role") == "tool")
        return {
            "role": "system",
            "content": (
                f"[{len(messages)} earlier messages summarized: "
                f"{user_msgs} user, {assistant_msgs} assistant, {tool_msgs} tool calls]"
            ),
        }
