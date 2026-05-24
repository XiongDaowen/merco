"""记忆召回机制"""

from .store import MemoryStore


class MemoryRecall:
    """记忆召回 - 根据上下文检索相关记忆"""

    def __init__(self, store: MemoryStore):
        self.store = store

    def recall(self, context: str, max_results: int = 5) -> list[dict]:
        """根据上下文召回相关记忆"""
        # 简单实现：基于关键词搜索
        results = self.store.search(context)
        return results[:max_results]

    def recall_by_tag(self, tag: str) -> list[dict]:
        """按标签召回记忆"""
        keys = self.store.list_keys(tag=tag)
        memories = []
        for key in keys:
            memory = self.store.load(key)
            if memory:
                memories.append(memory)
        return memories

    def get_relevant_context(self, query: str) -> str:
        """获取相关上下文文本"""
        memories = self.recall(query)
        if not memories:
            return ""

        context_parts = []
        for m in memories:
            context_parts.append(f"[{m['key']}]: {m['value']}")

        return "\n".join(context_parts)
