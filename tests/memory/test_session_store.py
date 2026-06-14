"""Tests for SessionStore: clone/set_title, get_children, and fault tolerance."""

import os
import tempfile
import pytest
from merco.memory.session_store import SessionStore, SessionWriteError


class TestSetTitle:
    def test_set_title_existing(self, tmp_path):
        """Setting title on an existing session returns True and updates title + updated_at."""
        db_path = str(tmp_path / "set_title_test.db")
        store = SessionStore(db_path)

        store.create_session("s1", title="Original")
        original = store.load_session("s1")
        original_updated = original["updated_at"]

        result = store.set_title("s1", "New Title")
        assert result is True

        updated = store.load_session("s1")
        assert updated["title"] == "New Title"
        # updated_at should be >= original (may be == if within same second)
        assert updated["updated_at"] >= original_updated

    def test_set_title_overwrite(self, tmp_path):
        """Overwriting an already-set title returns True and changes the title."""
        db_path = str(tmp_path / "set_title_overwrite.db")
        store = SessionStore(db_path)

        store.create_session("s1", title="First")
        result1 = store.set_title("s1", "Second")
        assert result1 is True
        assert store.load_session("s1")["title"] == "Second"

        result2 = store.set_title("s1", "Third")
        assert result2 is True
        assert store.load_session("s1")["title"] == "Third"

    def test_set_title_nonexistent(self, tmp_path):
        """Setting title on a nonexistent session returns False, does NOT crash."""
        db_path = str(tmp_path / "set_title_nonexistent.db")
        store = SessionStore(db_path)

        result = store.set_title("ghost-session", "Ghost Title")
        assert result is False


class TestCloneSession:
    def test_clone_copies_all_messages(self, tmp_path):
        """Clone a session with 2 messages — new_id differs, message count matches, parent_id is set."""
        db_path = str(tmp_path / "clone_test.db")
        store = SessionStore(db_path)

        # Create original session with 2 messages
        orig_id = "original-session-id"
        store.create_session(orig_id, title="Test Session")
        store.save_message(orig_id, "user", "Hello")
        store.save_message(orig_id, "assistant", "Hi there")

        # Clone it
        new_id = store.clone_session(orig_id)

        # new_id should differ from orig_id
        assert new_id != orig_id
        assert len(new_id) == 32  # uuid4 hex is 32 chars

        # Load both and verify
        orig = store.load_session(orig_id)
        cloned = store.load_session(new_id)

        assert orig is not None
        assert cloned is not None

        # Message count should match
        assert cloned["message_count"] == orig["message_count"] == 2

        # parent_id should point to original
        assert cloned["parent_id"] == orig_id

        # Title should match
        assert cloned["title"] == orig["title"]

        # Metadata should match
        assert cloned["metadata"] == orig["metadata"]

        # Messages should have same content (2 messages, same roles and content)
        assert len(cloned["messages"]) == 2
        assert cloned["messages"][0]["role"] == "user"
        assert cloned["messages"][0]["content"] == "Hello"
        assert cloned["messages"][1]["role"] == "assistant"
        assert cloned["messages"][1]["content"] == "Hi there"

    def test_clone_nonexistent_raises_value_error(self, tmp_path):
        """Cloning a nonexistent session should raise ValueError."""
        db_path = str(tmp_path / "clone_error.db")
        store = SessionStore(db_path)

        with pytest.raises(ValueError, match="Session not found"):
            store.clone_session("i-do-not-exist")

    def test_clone_empty_session(self, tmp_path):
        """Clone a session with no messages."""
        db_path = str(tmp_path / "clone_empty.db")
        store = SessionStore(db_path)

        orig_id = "empty-session"
        store.create_session(orig_id, title="Empty")

        new_id = store.clone_session(orig_id)

        assert new_id != orig_id

        cloned = store.load_session(new_id)
        assert cloned is not None
        assert cloned["message_count"] == 0
        assert cloned["parent_id"] == orig_id
        assert cloned["messages"] == []

    def test_clone_preserves_tool_calls_and_reasoning(self, tmp_path):
        """Clone a session with tool_calls, tool_call_id, and reasoning — verify preservation."""
        db_path = str(tmp_path / "clone_tool_calls.db")
        store = SessionStore(db_path)

        orig_id = "session-with-tools"
        store.create_session(orig_id, title="Tool Session")

        tool_calls = [
            {"id": "call_1", "name": "search_files", "arguments": {"pattern": "*.py"}}
        ]
        store.save_message(
            orig_id,
            "assistant",
            content="Let me search",
            tool_calls=tool_calls,
            reasoning="I need to find files",
        )
        store.save_message(
            orig_id,
            "tool",
            content='{"results": 3}',
            tool_call_id="call_1",
        )

        new_id = store.clone_session(orig_id)
        cloned = store.load_session(new_id)

        assert cloned is not None
        assert len(cloned["messages"]) == 2

        # assistant message
        assert cloned["messages"][0]["role"] == "assistant"
        assert cloned["messages"][0]["tool_call_id"] == ""
        assert cloned["messages"][0]["tool_calls"] == tool_calls
        assert cloned["messages"][0]["reasoning"] == "I need to find files"

        # tool message
        assert cloned["messages"][1]["role"] == "tool"
        assert cloned["messages"][1]["tool_call_id"] == "call_1"
        assert cloned["messages"][1]["tool_calls"] == []
        assert cloned["messages"][1]["reasoning"] == ""


class TestGetChildren:
    def test_get_children(self, tmp_path):
        db_path = str(tmp_path / "get_children_test.db")
        store = SessionStore(db_path)

        store.create_session("s1", title="Parent")
        child1_id = store.clone_session("s1")
        child2_id = store.clone_session("s1")
        children = store.get_children("s1")
        assert len(children) >= 2
        assert any(c["id"] == child1_id for c in children)
        assert any(c["id"] == child2_id for c in children)


class TestSaveMessageRetry:
    """测试 save_message 重试机制"""

    def test_save_message_success(self):
        """正常写入应该成功"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            store = SessionStore(db_path)
            store.create_session("test-session")

            msg_id = store.save_message("test-session", "user", "Hello")
            assert msg_id > 0

    def test_save_message_retries_on_operational_error(self, monkeypatch, tmp_path):
        """瞬时 OperationalError 应被重试，最终写入成功。"""
        import sqlite3

        db_path = str(tmp_path / "retry_test.db")
        store = SessionStore(db_path)
        store.create_session("test-session")

        call_count = {"n": 0}
        real_connect = sqlite3.connect

        def flaky_connect(*args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise sqlite3.OperationalError("database is locked")
            return real_connect(*args, **kwargs)

        monkeypatch.setattr(
            "merco.memory.session_store.sqlite3.connect", flaky_connect
        )

        msg_id = store.save_message("test-session", "user", "Hello")
        assert msg_id > 0
        assert call_count["n"] >= 2  # 至少重试了一次

    def test_save_message_raises_session_write_error_after_max_retries(
        self, monkeypatch, tmp_path
    ):
        """连续 OperationalError 超过 3 次后应抛出 SessionWriteError。"""
        import sqlite3

        db_path = str(tmp_path / "retry_exhaust_test.db")
        store = SessionStore(db_path)
        store.create_session("test-session")

        def always_fail(*args, **kwargs):
            raise sqlite3.OperationalError("database is locked")

        monkeypatch.setattr(
            "merco.memory.session_store.sqlite3.connect", always_fail
        )

        with pytest.raises(SessionWriteError):
            store.save_message("test-session", "user", "Hello")


class TestBackupRestore:
    """测试备份恢复"""

    def test_backup_creates_file(self):
        """备份应该创建 .backup 文件"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            store = SessionStore(db_path)
            store.create_session("test-session")
            store.save_message("test-session", "user", "Hello")

            result = store.backup()
            assert result is True
            assert os.path.exists(db_path + ".backup")

    def test_restore_from_backup(self):
        """应该能从备份恢复"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            store = SessionStore(db_path)
            store.create_session("test-session")
            store.save_message("test-session", "user", "Hello")

            # 创建备份
            store.backup()

            # 删除原文件
            os.remove(db_path)

            # 恢复
            result = store.restore_from_backup()
            assert result is True
            assert os.path.exists(db_path)

            # 验证数据
            session = store.load_session("test-session")
            assert session is not None
            assert len(session["messages"]) == 1


class TestIntegrityCheck:
    """测试完整性检查"""

    def test_check_integrity_normal(self):
        """正常的数据库应该通过检查"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            store = SessionStore(db_path)
            store.create_session("test-session")

            result = store.check_integrity()
            assert result is True
