"""CacheOptimizeProcessor — 提高 LLM 缓存命中率"""
from __future__ import annotations

from merco.context.pipeline import ContextProcessor


class CacheOptimizeProcessor(ContextProcessor):
    """缓存优化：重排序让稳定内容在前"""
    name = "cache_optimize"

    async def process(self, messages: list[dict], **kwargs) -> list[dict]:
        stable = []
        volatile = []

        for msg in messages:
            if self._is_stable(msg):
                stable.append(msg)
            else:
                volatile.append(msg)

        return stable + volatile

    def _is_stable(self, msg: dict) -> bool:
        """判断消息是否稳定（可缓存）"""
        role = msg.get("role", "")
        if role == "system":
            return True
        content = str(msg.get("content", ""))
        if "[Earlier conversation summary]" in content:
            return True
        if "[memory]" in content:
            return True
        return False
