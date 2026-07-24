"""Memory recall interfaces — ABC + FTS5 + Memory + Hybrid recallers."""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .session_search import SessionSearch

from .store import MemoryStore


@dataclass
class RecallResult:
    """A single recall result from any recaller."""

    snippet: str
    session_title: str = ""
    score: float = 0.0
    source: str = "memory"  # "fts5" | "memory"


class BaseRecaller(ABC):
    """Abstract base for all recallers."""

    name: str = ""

    @abstractmethod
    async def recall(self, query: str, limit: int = 10) -> list[RecallResult]:
        """Return recall results for the given query."""
        ...


class FTS5Recaller(BaseRecaller):
    """Full-text search recaller backed by SessionSearch."""

    name = "fts5"

    def __init__(self, session_search: SessionSearch) -> None:
        self._search = session_search

    async def recall(self, query: str, limit: int = 10) -> list[RecallResult]:
        raw = self._search.search(query, limit=limit)
        total = len(raw)
        results: list[RecallResult] = []
        for i, item in enumerate(raw):
            score = (total - i) / max(total, 1) if total > 0 else 0.0
            results.append(
                RecallResult(
                    snippet=item["snippet"],
                    session_title=item.get("session_title", ""),
                    score=round(score, 4),
                    source="fts5",
                )
            )
        return results


class MemoryRecaller(BaseRecaller):
    """Key-value memory store recaller backed by MemoryStore."""

    name = "memory"

    def __init__(self, memory_store: MemoryStore) -> None:
        self._store = memory_store

    async def recall(self, query: str, limit: int = 10) -> list[RecallResult]:
        raw = self._store.search(query)[:limit]
        total = len(raw)
        results: list[RecallResult] = []
        for i, item in enumerate(raw):
            score = (total - i) / max(total, 1) if total > 0 else 0.0
            snippet = item.get("value", "")
            if isinstance(snippet, (dict, list)):
                snippet = json.dumps(snippet, ensure_ascii=False)
            else:
                snippet = str(snippet)
            results.append(
                RecallResult(
                    snippet=snippet,
                    session_title=item.get("key", ""),
                    score=round(score, 4),
                    source="memory",
                )
            )
        return results


class HybridRecaller(BaseRecaller):
    """Aggregates multiple recallers, deduplicates, and limits by chars.

    Caches results by (query, limit) so repeated calls return instantly.
    """

    name = "hybrid"

    def __init__(
        self,
        recallers: list[BaseRecaller] | None = None,
        limit: int = 3,
        max_chars: int = 300,
    ) -> None:
        self._recallers: list[BaseRecaller] = list(recallers) if recallers else []
        self._limit = limit
        self._max_chars = max_chars
        self._cache: dict[tuple[str, int], list[RecallResult]] = {}

    def add(self, recaller: BaseRecaller) -> HybridRecaller:
        """Add a recaller (fluent interface)."""
        self._recallers.append(recaller)
        return self

    async def recall(self, query: str, limit: int = 10) -> list[RecallResult]:
        cache_key = (query, limit)
        if cache_key in self._cache:
            return self._cache[cache_key]

        # Gather from all recallers
        all_results: list[RecallResult] = []
        for rec in self._recallers:
            try:
                batch = await rec.recall(query, limit=limit)
                all_results.extend(batch)
            except Exception:
                # Swallow individual recaller errors so one failure
                # doesn't break the whole hybrid pipeline.
                logger = logging.getLogger(__name__)
                logger.warning("Recaller %s failed for query %r", rec.name, query, exc_info=True)
                continue

        # Sort by score descending
        all_results.sort(key=lambda r: r.score, reverse=True)

        # Deduplicate by first 80 chars of snippet
        seen: set[str] = set()
        deduped: list[RecallResult] = []
        for r in all_results:
            prefix = r.snippet[:80]
            if prefix not in seen:
                seen.add(prefix)
                deduped.append(r)

        # Truncate by max_chars (cumulative snippet length)
        total_chars = 0
        truncated: list[RecallResult] = []
        for r in deduped:
            total_chars += len(r.snippet)
            if total_chars > self._max_chars and truncated:
                break
            truncated.append(r)

        # Apply top-level limit (use _limit as a cap, not a floor)
        final = truncated[: min(limit, self._limit)]

        self._cache[cache_key] = final
        return final


# ---------------------------------------------------------------------------
# Backward-compatible synchronous MemoryRecall (existing API)
# ---------------------------------------------------------------------------


class MemoryRecall:
    """Legacy memory recall — kept for backward compatibility.

    Prefer MemoryRecaller (async) for new code.
    """

    def __init__(self, store: MemoryStore) -> None:
        self.store = store

    def recall(self, context: str, max_results: int = 5) -> list[dict]:
        """根据上下文召回相关记忆"""
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
            context_parts.append(f"[{m.get('key', '?')}]: {m.get('value', '')}")

        return "\n".join(context_parts)
