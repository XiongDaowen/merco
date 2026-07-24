"""快照系统单元测试"""

import json
import tempfile
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from merco.sandbox import snapshot


class TestSnapshot:
    """快照系统测试"""

    @pytest.fixture(autouse=True)
    def setup_teardown(self, monkeypatch):
        """设置和清理：使用临时目录作为快照存储"""
        # 替换快照存储目录为临时目录
        with tempfile.TemporaryDirectory() as tmpdir:
            monkeypatch.setattr(snapshot, "SNAPSHOT_DIR", snapshot.Path(tmpdir))
            # 重置当前会话ID
            snapshot.set_current_session(None)
            yield

    def test_set_get_current_session(self):
        """测试设置和获取当前会话ID"""
        assert snapshot.get_current_session() is None

        session_id = "test-session-123"
        snapshot.set_current_session(session_id)
        assert snapshot.get_current_session() == session_id

    def test_track_with_explicit_session_id(self):
        """测试使用显式会话ID记录快照"""
        session_id = "test-session-2024"
        test_path = "/test/file.txt"
        test_content = "original content"

        # 记录快照
        result = snapshot.track(test_path, test_content, session_id=session_id)

        # 验证返回结果
        assert result["session_id"] == session_id
        assert result["snapshot_id"] == 0
        assert result["path"] == str(snapshot.Path(test_path).resolve())
        assert "timestamp" in result

        # 验证文件被保存
        session_file = snapshot._session_path(session_id)
        assert session_file.exists()
        saved_data = json.loads(session_file.read_text())
        assert len(saved_data) == 1
        assert saved_data[0]["path"] == str(snapshot.Path(test_path).resolve())
        assert saved_data[0]["content"] == test_content

    def test_track_without_session_id_uses_default(self):
        """测试不提供会话ID时自动生成"""
        test_path = "/test/file.txt"
        test_content = "original content"

        # 记录快照
        result = snapshot.track(test_path, test_content)
        session_id = result["session_id"]

        # 验证会话ID是自动生成的格式
        assert len(session_id) > 0
        # 验证快照被保存
        assert snapshot._session_path(session_id).exists()

    def test_track_multiple_snapshots_same_session(self):
        """测试同一会话记录多个快照"""
        session_id = "multi-snapshot-test"
        test_path1 = "/test/file1.txt"
        test_content1 = "content 1"
        test_path2 = "/test/file2.txt"
        test_content2 = "content 2"

        # 记录第一个快照
        result1 = snapshot.track(test_path1, test_content1, session_id=session_id)
        assert result1["snapshot_id"] == 0

        # 记录第二个快照
        result2 = snapshot.track(test_path2, test_content2, session_id=session_id)
        assert result2["snapshot_id"] == 1

        # 验证两个快照都被保存
        saved_data = snapshot._load(session_id)
        assert len(saved_data) == 2
        assert saved_data[0]["path"] == str(snapshot.Path(test_path1).resolve())
        assert saved_data[1]["path"] == str(snapshot.Path(test_path2).resolve())

    def test_history(self):
        """测试查询会话历史"""
        session_id = "history-test"
        test_path = "/test/file.txt"
        test_content = "test content"

        # 记录快照
        snapshot.track(test_path, test_content, session_id=session_id)

        # 查询历史
        history = snapshot.history(session_id)
        assert len(history) == 1
        assert history[0]["path"] == str(snapshot.Path(test_path).resolve())
        assert history[0]["content"] == test_content
        assert "timestamp" in history[0]

        # 查询不存在的会话
        assert snapshot.history("nonexistent-session") == []

    def test_list_sessions(self):
        """测试列出所有会话"""
        # 初始为空
        assert snapshot.list_sessions() == []

        # 创建两个会话
        session1 = "session-1"
        session2 = "session-2"
        snapshot.track("/test/file1.txt", "content1", session_id=session1)
        # 等待一点时间，确保时间戳不同
        import time

        time.sleep(0.01)
        snapshot.track("/test/file2.txt", "content2", session_id=session2)
        snapshot.track("/test/file3.txt", "content3", session_id=session2)

        # 列出会话（按时间倒序）
        sessions = snapshot.list_sessions()
        assert len(sessions) == 2
        # 最新的会话排在前面
        assert sessions[0]["session_id"] == session2
        assert sessions[0]["file_count"] == 2
        assert sessions[1]["session_id"] == session1
        assert sessions[1]["file_count"] == 1

    def test_revert_all_snapshots(self, tmp_path):
        """测试撤销会话的所有快照"""
        session_id = "revert-all-test"
        # 创建测试文件
        test_file = tmp_path / "test.txt"
        test_file.write_text("modified content")
        original_content = "original content"

        # 记录快照
        snapshot.track(str(test_file), original_content, session_id=session_id)

        # 撤销所有
        results = snapshot.revert(session_id)

        # 验证撤销结果
        assert len(results) == 1
        assert results[0]["path"] == str(test_file.resolve())
        assert results[0]["reverted"] is True
        assert results[0]["error"] is None
        # 验证文件内容被恢复
        assert test_file.read_text() == original_content
        # 验证会话文件被删除
        assert not snapshot._session_path(session_id).exists()

    def test_revert_single_snapshot(self, tmp_path):
        """测试撤销单个快照"""
        session_id = "revert-single-test"
        # 创建两个测试文件
        file1 = tmp_path / "file1.txt"
        file2 = tmp_path / "file2.txt"
        file1.write_text("modified 1")
        file2.write_text("modified 2")
        original1 = "original 1"
        original2 = "original 2"

        # 记录两个快照
        snapshot.track(str(file1), original1, session_id=session_id)
        snapshot.track(str(file2), original2, session_id=session_id)

        # 只撤销第二个快照
        results = snapshot.revert(session_id, snapshot_index=1)

        # 验证结果
        assert len(results) == 1
        assert results[0]["path"] == str(file2.resolve())
        # file2被恢复，file1没有
        assert file2.read_text() == original2
        assert file1.read_text() == "modified 1"
        # 会话文件仍然存在
        assert snapshot._session_path(session_id).exists()

    def test_revert_nonexistent_session(self):
        """测试撤销不存在的会话"""
        results = snapshot.revert("nonexistent-session")
        assert results == []

    def test_revert_invalid_snapshot_index(self):
        """测试撤销无效的快照索引"""
        session_id = "invalid-index-test"
        snapshot.track("/test/file.txt", "content", session_id=session_id)

        # 索引超出范围会抛出IndexError
        with pytest.raises(IndexError):
            snapshot.revert(session_id, snapshot_index=999)

    def test_revert_file_write_error(self, tmp_path, caplog):
        """测试撤销时文件写入错误"""
        session_id = "revert-error-test"
        # 创建一个目录而不是文件，模拟写入错误
        test_path = tmp_path / "testdir"
        test_path.mkdir()
        original_content = "content"

        # 记录快照
        snapshot.track(str(test_path), original_content, session_id=session_id)

        # 撤销（会失败，因为路径是目录）
        results = snapshot.revert(session_id)

        # 验证错误处理
        assert len(results) == 1
        assert results[0]["path"] == str(test_path.resolve())
        assert results[0]["reverted"] is False
        assert "Is a directory" in results[0]["error"]
        # 会话文件不会被删除
        assert snapshot._session_path(session_id).exists()

    def test_revert_partial_failure_keeps_session(self, tmp_path):
        """测试部分失败时保留会话文件（回归测试 - Bug #1）

        场景：批量撤销中，部分文件回退失败时，会话文件应保留以便重试。
        """
        session_id = "partial-failure-test"

        # 文件1：正常文件，可成功回退
        good_file = tmp_path / "good.txt"
        good_file.write_text("modified good")

        # 文件2：用一个会写入失败的目录
        bad_path = tmp_path / "baddir"
        bad_path.mkdir()

        snapshot.track(str(good_file), "original good", session_id=session_id)
        snapshot.track(str(bad_path), "original bad", session_id=session_id)

        results = snapshot.revert(session_id)

        # 两个条目都应该返回
        assert len(results) == 2
        reverted_status = {r["path"]: r["reverted"] for r in results}
        assert reverted_status[str(good_file.resolve())] is True
        assert reverted_status[str(bad_path.resolve())] is False

        # 即使成功条数 >= 1，只要有任何失败，会话文件仍应保留
        assert snapshot._session_path(session_id).exists()

        # 重试时只撤销失败的那条
        retry_results = snapshot.revert(session_id, snapshot_index=1)
        assert len(retry_results) == 1
        assert retry_results[0]["reverted"] is False

    def test_load_corrupted_json_file(self):
        """测试加载损坏的JSON文件"""
        session_id = "corrupted-test"
        session_file = snapshot._session_path(session_id)
        # 写入无效的JSON
        session_file.write_text("{invalid json}")

        # 加载应该返回空列表，不抛出异常
        assert snapshot._load(session_id) == []

    @patch("merco.sandbox.snapshot.datetime")
    def test_default_session_id_format(self, mock_datetime):
        """测试自动生成的会话ID格式"""
        mock_now = MagicMock()
        mock_now.strftime.return_value = "20240101_120000_123456"
        mock_now.isoformat.return_value = "2024-01-01T12:00:00.123456+00:00"
        mock_datetime.now.return_value = mock_now
        mock_datetime.fromtimestamp = datetime.fromtimestamp

        result = snapshot.track("/test/file.txt", "content")
        assert result["session_id"] == "20240101_120000_123456"
        assert result["timestamp"] == "2024-01-01T12:00:00.123456+00:00"
