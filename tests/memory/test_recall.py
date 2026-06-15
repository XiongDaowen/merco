"""Tests for memory recall interfaces."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from merco.memory.recall import (
    RecallResult,
    BaseRecaller,
    FTS5Recaller,
    MemoryRecaller,
    HybridRecaller,
)


class TestRecallResult:
    def test_create_full(self):
        r = RecallResult(
            snippet="hello world",
            session_title="My Session",
            score=0.95,
            source="fts5",
        )
        assert r.snippet == "hello world"
        assert r.session_title == "My Session"
        assert r.score == 0.95
        assert r.source == "fts5"

    def test_defaults(self):
        r = RecallResult(snippet="x")
        assert r.session_title == ""
        assert r.score == 0.0
        assert r.source == "memory"

    def test_is_dataclass(self):
        r1 = RecallResult(snippet="a", score=0.5)
        r2 = RecallResult(snippet="a", score=0.5)
        assert r1 == r2
        assert r1 != RecallResult(snippet="a", score=0.9)


class TestBaseRecaller:
    def test_cannot_instantiate_abstract(self):
        with pytest.raises(TypeError):
            BaseRecaller()  # noqa

    def test_concrete_subclass(self):
        class Simple(BaseRecaller):
            name = "simple"

            async def recall(self, query, limit=10):
                return [RecallResult(snippet=query)]

        rec = Simple()
        assert rec.name == "simple"

    def test_default_name(self):
        class NoName(BaseRecaller):
            async def recall(self, query, limit=10):
                return []

        rec = NoName()
        assert rec.name == ""


class TestFTS5Recaller:
    @pytest.mark.asyncio
    async def test_recall_wraps_search_results(self):
        mock_search = MagicMock()
        mock_search.search.return_value = [
            {
                "id": 1,
                "session_id": "s1",
                "session_title": "My Session",
                "role": "user",
                "snippet": "hello world",
                "timestamp": "2024-01-01",
            },
            {
                "id": 2,
                "session_id": "s2",
                "session_title": "Other",
                "role": "assistant",
                "snippet": "foo bar",
                "timestamp": "2024-01-02",
            },
        ]

        rec = FTS5Recaller(mock_search)
        results = await rec.recall("hello", limit=5)

        assert len(results) == 2
        assert results[0].snippet == "hello world"
        assert results[0].session_title == "My Session"
        assert results[0].source == "fts5"
        assert results[0].score > results[1].score
        mock_search.search.assert_called_once_with("hello", limit=5)

    @pytest.mark.asyncio
    async def test_recall_empty(self):
        mock_search = MagicMock()
        mock_search.search.return_value = []

        rec = FTS5Recaller(mock_search)
        results = await rec.recall("nothing", limit=5)
        assert results == []

    @pytest.mark.asyncio
    async def test_recall_score_descending(self):
        mock_search = MagicMock()
        mock_search.search.return_value = [
            {
                "id": i,
                "session_id": f"s{i}",
                "session_title": f"Title {i}",
                "role": "user",
                "snippet": f"result {i}",
                "timestamp": "2024-01-01",
            }
            for i in range(5)
        ]

        rec = FTS5Recaller(mock_search)
        results = await rec.recall("query", limit=10)

        scores = [r.score for r in results]
        assert scores == sorted(scores, reverse=True)
        assert all(0 <= s <= 1.0 for s in scores)

    def test_name(self):
        rec = FTS5Recaller(MagicMock())
        assert rec.name == "fts5"


class TestMemoryRecaller:
    @pytest.mark.asyncio
    async def test_recall_wraps_store_results(self):
        mock_store = MagicMock()
        mock_store.search.return_value = [
            {
                "key": "note-1",
                "value": {"text": "important note"},
                "tags": ["a"],
                "created_at": "2024-01-01",
            },
            {
                "key": "note-2",
                "value": {"text": "another thing"},
                "tags": ["b"],
                "created_at": "2024-01-02",
            },
        ]

        rec = MemoryRecaller(mock_store)
        results = await rec.recall("important", limit=5)

        assert len(results) == 2
        assert results[0].session_title == "note-1"
        assert results[0].source == "memory"
        mock_store.search.assert_called_once_with("important")

    @pytest.mark.asyncio
    async def test_recall_empty(self):
        mock_store = MagicMock()
        mock_store.search.return_value = []

        rec = MemoryRecaller(mock_store)
        results = await rec.recall("nothing", limit=5)
        assert results == []

    @pytest.mark.asyncio
    async def test_recall_score_descending(self):
        mock_store = MagicMock()
        mock_store.search.return_value = [
            {
                "key": f"k{i}",
                "value": {"text": f"v{i}"},
                "tags": [],
                "created_at": "2024-01-01",
            }
            for i in range(3)
        ]

        rec = MemoryRecaller(mock_store)
        results = await rec.recall("query", limit=10)

        scores = [r.score for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_name(self):
        rec = MemoryRecaller(MagicMock())
        assert rec.name == "memory"


class TestHybridRecaller:
    @pytest.mark.asyncio
    async def test_aggregates_and_sorts(self):
        r1 = MagicMock()
        r1.name = "fts5"
        r1.recall = AsyncMock(
            return_value=[
                RecallResult(snippet="fts A", session_title="SA", score=0.9, source="fts5"),
                RecallResult(snippet="fts B", session_title="SB", score=0.5, source="fts5"),
            ]
        )
        r2 = MagicMock()
        r2.name = "memory"
        r2.recall = AsyncMock(
            return_value=[
                RecallResult(snippet="mem A", session_title="SC", score=0.8, source="memory"),
            ]
        )

        hybrid = HybridRecaller([r1, r2], limit=3)
        results = await hybrid.recall("query", limit=3)

        assert len(results) == 3
        scores = [r.score for r in results]
        assert scores == sorted(scores, reverse=True)

    @pytest.mark.asyncio
    async def test_deduplicates_by_first_80_chars(self):
        snippet = "this is a very long snippet that will be duplicated across recallers " * 3
        r1 = MagicMock()
        r1.name = "fts5"
        r1.recall = AsyncMock(
            return_value=[
                RecallResult(snippet=snippet, session_title="A", score=0.9, source="fts5"),
            ]
        )
        r2 = MagicMock()
        r2.name = "memory"
        r2.recall = AsyncMock(
            return_value=[
                RecallResult(snippet=snippet + " extra", session_title="B", score=0.8, source="memory"),
            ]
        )

        hybrid = HybridRecaller([r1, r2], limit=3)
        results = await hybrid.recall("python", limit=3)

        # first 80 chars match => deduplicated, higher score kept
        assert len(results) == 1
        assert results[0].score == 0.9

    @pytest.mark.asyncio
    async def test_different_prefix_not_deduplicated(self):
        r1 = MagicMock()
        r1.name = "fts5"
        r1.recall = AsyncMock(
            return_value=[
                RecallResult(snippet="A" * 80 + "unique1", session_title="T", score=0.9, source="fts5"),
            ]
        )
        r2 = MagicMock()
        r2.name = "memory"
        r2.recall = AsyncMock(
            return_value=[
                RecallResult(snippet="B" * 80 + "unique2", session_title="T", score=0.8, source="memory"),
            ]
        )

        hybrid = HybridRecaller([r1, r2], limit=3)
        results = await hybrid.recall("query", limit=3)

        # different first 80 chars => both kept
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_max_chars_limits_cumulative_length(self):
        r1 = MagicMock()
        r1.name = "fts5"
        r1.recall = AsyncMock(
            return_value=[
                RecallResult(snippet="Hello World", session_title="T1", score=1.0, source="fts5"),
                RecallResult(snippet="Foo Bar Baz", session_title="T2", score=0.9, source="fts5"),
                RecallResult(snippet="Longer snippet", session_title="T3", score=0.8, source="fts5"),
            ]
        )

        hybrid = HybridRecaller([r1], limit=5, max_chars=25)
        results = await hybrid.recall("query", limit=5)

        # "Hello World" = 11 chars => total 11, fits
        # + "Foo Bar Baz" = 11 chars => total 22, fits
        # + "Longer snippet" = 14 chars => total 36 > 25, excluded
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_caches_by_query_and_limit(self):
        r1 = MagicMock()
        r1.name = "fts5"
        r1.recall = AsyncMock(
            return_value=[
                RecallResult(snippet="cached", session_title="T", score=1.0, source="fts5"),
            ]
        )

        hybrid = HybridRecaller([r1], limit=2)
        results1 = await hybrid.recall("cache test", limit=2)
        results2 = await hybrid.recall("cache test", limit=2)

        assert results1 == results2
        r1.recall.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_different_query_not_cached(self):
        r1 = MagicMock()
        r1.name = "fts5"
        r1.recall = AsyncMock(
            return_value=[
                RecallResult(snippet="x", session_title="T", score=1.0, source="fts5"),
            ]
        )

        hybrid = HybridRecaller([r1], limit=2)
        await hybrid.recall("query1", limit=2)
        await hybrid.recall("query2", limit=2)

        assert r1.recall.await_count == 2

    @pytest.mark.asyncio
    async def test_different_limit_not_cached(self):
        r1 = MagicMock()
        r1.name = "fts5"
        r1.recall = AsyncMock(
            return_value=[
                RecallResult(snippet="x", session_title="T", score=1.0, source="fts5"),
            ]
        )

        hybrid = HybridRecaller([r1], limit=2)
        await hybrid.recall("query", limit=2)
        await hybrid.recall("query", limit=5)

        assert r1.recall.await_count == 2

    def test_add_fluent(self):
        hybrid = HybridRecaller([])
        r = MagicMock()
        r.name = "extra"
        result = hybrid.add(r)
        assert result is hybrid
        assert len(hybrid._recallers) == 1

    @pytest.mark.asyncio
    async def test_empty_recallers(self):
        hybrid = HybridRecaller([])
        results = await hybrid.recall("anything", limit=5)
        assert results == []

    @pytest.mark.asyncio
    async def test_hybrid_with_real_store_and_search(self, tmp_path):
        """HybridRecaller 聚合 FTS5Recaller + MemoryRecaller，从真实数据召回"""
        from merco.memory.store import MemoryStore
        from merco.memory.session_store import SessionStore
        from merco.memory.session_search import SessionSearch

        # 真实 store
        session_store = SessionStore(str(tmp_path / "sess.db"))
        mem_store = MemoryStore(str(tmp_path / "memory"))

        # 先创建 session（save_message 有 FK 约束）
        session_store.create_session("s1")

        # 写入 session message
        session_store.save_message("s1", "user", "Python programming")
        session_store.save_message("s1", "assistant", "I can help with Python")
        session_store.save_message("s1", "user", "Java is also good")

        # 写入 memory（value 需 JSON-serializable）
        mem_store.save("user_lang", {"text": "Python"}, tags=["[user]"])

        # 构造 HybridRecaller
        fts5 = FTS5Recaller(SessionSearch(session_store))
        mem = MemoryRecaller(mem_store)
        hybrid = HybridRecaller(limit=5, max_chars=500).add(fts5).add(mem)

        # 召回
        results = await hybrid.recall("Python", limit=5)
        assert len(results) >= 1

        # 验证 source 字段标识
        sources = {r.source for r in results}
        assert "fts5" in sources or "memory" in sources
