"""Tests for SessionStore.clone_session() and SessionStore.set_title()"""

import pytest
from merco.memory.session_store import SessionStore


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
