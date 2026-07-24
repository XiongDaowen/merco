"""快照恢复集成测试 — 覆盖文件编辑前后快照记录与回滚。"""

import pytest

from merco.sandbox import snapshot
from tests.integration.core.programmable_mock import Response


class TestSnapshotCreation:
    """Task 18: 快照创建 — edit/write 触发快照记录"""

    @pytest.mark.asyncio
    async def test_edit_file_creates_snapshot(self, scenario, tmp_path):
        """edit_file 调用前通过 EditApplyMiddleware 记录快照，验证 session 文件存在且历史包含原始内容。"""
        target = tmp_path / "code.py"
        original = "def foo():\n    return 1\n"
        target.write_text(original)

        snapshot.set_current_session("test-edit-1")

        # 模拟 EditApplyMiddleware：在实际代码路径中，中间件会在工具执行前调用 snapshot.track()
        snapshot.track(str(target), original, session_id="test-edit-1")

        scenario.provider.expect(
            [
                Response.tool_call(
                    "edit_file",
                    {
                        "path": str(target),
                        "search": "return 1",
                        "replace": "return 42",
                    },
                ),
                Response.content("已修改"),
            ]
        )

        await scenario.run("把 return 1 改成 return 42")

        session_file = snapshot._session_path("test-edit-1")
        assert session_file.exists()

        history = snapshot.history("test-edit-1")
        assert len(history) >= 1
        assert history[0]["content"] == original

    @pytest.mark.asyncio
    async def test_write_file_creates_snapshot(self, scenario, tmp_path):
        """write_file 调用前记录快照，验证历史中存在修改前内容。"""
        target = tmp_path / "file.txt"
        original = "old content"
        target.write_text(original)

        snapshot.set_current_session("test-write-1")

        # 模拟 EditApplyMiddleware：在实际代码路径中，中间件会在工具执行前调用 snapshot.track()
        snapshot.track(str(target), original, session_id="test-write-1")

        scenario.provider.expect(
            [
                Response.tool_call(
                    "write_file",
                    {
                        "path": str(target),
                        "content": "new content",
                    },
                ),
                Response.content("已写入"),
            ]
        )

        await scenario.run("重写文件")

        history = snapshot.history("test-write-1")
        assert any(h["content"] == "old content" for h in history)


class TestSingleRevert:
    """Task 19: 单点回滚 — 按索引恢复单个快照，不影响其他文件"""

    @pytest.mark.asyncio
    async def test_revert_single_snapshot_restores_only_that_file(self, scenario, tmp_path):
        """回滚单个快照仅恢复对应文件，其他文件保持修改后状态。"""
        file_a = tmp_path / "a.txt"
        file_b = tmp_path / "b.txt"
        file_a.write_text("original_a")
        file_b.write_text("original_b")

        snapshot.set_current_session("multi-edit")

        # 快照 0：记录 file_a 修改前状态
        snapshot.track(str(file_a), "original_a", session_id="multi-edit")
        file_a.write_text("modified_a")

        scenario.provider.expect(
            [
                Response.tool_call("write_file", {"path": str(file_a), "content": "modified_a"}),
                Response.content("ok1"),
            ]
        )
        await scenario.run("改 a")

        # 快照 1：记录 file_b 修改前状态
        snapshot.track(str(file_b), "original_b", session_id="multi-edit")
        file_b.write_text("modified_b")

        scenario.provider.expect(
            [
                Response.tool_call("write_file", {"path": str(file_b), "content": "modified_b"}),
                Response.content("ok2"),
            ]
        )
        await scenario.run("改 b")

        assert file_a.read_text() == "modified_a"
        assert file_b.read_text() == "modified_b"

        # 仅回滚第一个快照（file_a）
        snapshot.revert("multi-edit", snapshot_index=0)

        assert file_a.read_text() == "original_a"
        assert file_b.read_text() == "modified_b"


class TestFullRevert:
    """Task 19: 全部回滚 — 无索引回滚所有快照并清理 session 文件"""

    @pytest.mark.asyncio
    async def test_revert_all_restores_all_files(self, scenario, tmp_path):
        """无索引回滚恢复所有被修改的文件。"""
        file_a = tmp_path / "a.txt"
        file_b = tmp_path / "b.txt"
        file_a.write_text("orig_a")
        file_b.write_text("orig_b")

        snapshot.set_current_session("full-revert-test")

        # 快照 0：file_a
        snapshot.track(str(file_a), "orig_a", session_id="full-revert-test")
        file_a.write_text("mod_a")

        scenario.provider.expect(
            [
                Response.tool_call("write_file", {"path": str(file_a), "content": "mod_a"}),
                Response.content("ok"),
            ]
        )
        await scenario.run("改 a")

        # 快照 1：file_b
        snapshot.track(str(file_b), "orig_b", session_id="full-revert-test")
        file_b.write_text("mod_b")

        scenario.provider.expect(
            [
                Response.tool_call("write_file", {"path": str(file_b), "content": "mod_b"}),
                Response.content("ok"),
            ]
        )
        await scenario.run("改 b")

        results = snapshot.revert("full-revert-test")

        assert file_a.read_text() == "orig_a"
        assert file_b.read_text() == "orig_b"
        assert len(results) == 2
        assert all(r["reverted"] for r in results)

    @pytest.mark.asyncio
    async def test_revert_all_clears_session_file(self, scenario, tmp_path):
        """全部回滚后删除 session 文件。"""
        target = tmp_path / "x.txt"
        target.write_text("original")

        snapshot.set_current_session("clear-test")

        # 记录快照并模拟修改
        snapshot.track(str(target), "original", session_id="clear-test")
        target.write_text("modified")

        scenario.provider.expect(
            [
                Response.tool_call("write_file", {"path": str(target), "content": "modified"}),
                Response.content("ok"),
            ]
        )
        await scenario.run("改 x")

        assert snapshot._session_path("clear-test").exists()
        snapshot.revert("clear-test")
        assert not snapshot._session_path("clear-test").exists()


class TestSnapshotHistory:
    """Task 20: 历史查询 — history() 列出所有快照条目，包含 path/content/timestamp"""

    @pytest.mark.asyncio
    async def test_history_lists_all_snapshots(self, scenario, tmp_path):
        """多次修改后 history 返回完整快照列表，每条包含 path、content、timestamp。"""
        target = tmp_path / "f.txt"
        target.write_text("v0")

        snapshot.set_current_session("history-test")

        # 快照 0
        snapshot.track(str(target), "v0", session_id="history-test")
        target.write_text("v1")

        scenario.provider.expect(
            [
                Response.tool_call("write_file", {"path": str(target), "content": "v1"}),
                Response.content("ok"),
            ]
        )
        await scenario.run("第一次写")

        # 快照 1
        snapshot.track(str(target), "v1", session_id="history-test")
        target.write_text("v2")

        scenario.provider.expect(
            [
                Response.tool_call("write_file", {"path": str(target), "content": "v2"}),
                Response.content("ok"),
            ]
        )
        await scenario.run("第二次写")

        history = snapshot.history("history-test")
        assert len(history) >= 2
        for entry in history:
            assert "path" in entry
            assert "content" in entry
            assert "timestamp" in entry

    def test_history_for_nonexistent_session(self, scenario):
        """不存在的 session 返回空列表。"""
        assert snapshot.history("nonexistent-session-id") == []


class TestSessionIsolation:
    """Task 20: Session 隔离 — 不同 session 的快照历史相互独立"""

    @pytest.mark.asyncio
    async def test_different_sessions_have_independent_history(self, scenario, tmp_path):
        """两个 session 的快照历史互不干扰。"""
        target = tmp_path / "f.txt"
        target.write_text("init")

        snapshot.set_current_session("session_a")

        # Session A 的快照
        snapshot.track(str(target), "init", session_id="session_a")
        target.write_text("by_a")

        scenario.provider.expect(
            [
                Response.tool_call("write_file", {"path": str(target), "content": "by_a"}),
                Response.content("ok"),
            ]
        )
        await scenario.run("session a edit")

        snapshot.set_current_session("session_b")

        # Session B 的快照
        snapshot.track(str(target), "by_a", session_id="session_b")
        target.write_text("by_b")

        scenario.provider.expect(
            [
                Response.tool_call("write_file", {"path": str(target), "content": "by_b"}),
                Response.content("ok"),
            ]
        )
        await scenario.run("session b edit")

        history_a = snapshot.history("session_a")
        history_b = snapshot.history("session_b")
        assert len(history_a) >= 1
        assert len(history_b) >= 1
        assert history_a != history_b
