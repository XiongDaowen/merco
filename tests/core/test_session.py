"""Tests for Session.fork() classmethod."""

import pytest
from merco.core.session import Session
from merco.memory.session_store import SessionStore


class TestSessionFork:
    def test_fork_creates_new_session(self, tmp_path):
        """Fork creates a new session with different ID and copies messages."""
        db_path = str(tmp_path / "fork_test.db")
        store = SessionStore(db_path)

        # Create original session with 2 messages
        orig_id = "original-abc"
        store.create_session(orig_id, title="My Session")
        store.save_message(orig_id, "user", "Hello")
        store.save_message(orig_id, "assistant", "Hi there")

        # Fork it
        forked = Session.fork(orig_id, store)

        assert forked is not None
        assert forked.id != orig_id
        assert len(forked.messages) == 2
        assert forked.title == "My Session"

    def test_fork_copies_messages(self, tmp_path):
        """Forked session has identical message content."""
        db_path = str(tmp_path / "fork_msgs.db")
        store = SessionStore(db_path)

        orig_id = "original-xyz"
        store.create_session(orig_id, title="Msg Test")
        store.save_message(orig_id, "user", "Q1")
        store.save_message(orig_id, "assistant", "A1", reasoning="thinking...")
        store.save_message(orig_id, "user", "Q2")

        forked = Session.fork(orig_id, store)

        assert forked is not None
        assert len(forked.messages) == 3
        assert forked.messages[0]["role"] == "user"
        assert forked.messages[0]["content"] == "Q1"
        assert forked.messages[1]["role"] == "assistant"
        assert forked.messages[1]["content"] == "A1"
        assert forked.messages[1]["reasoning"] == "thinking..."
        assert forked.messages[2]["role"] == "user"

    def test_fork_preserves_title(self, tmp_path):
        """Fork preserves the original title when no custom title given."""
        db_path = str(tmp_path / "fork_title.db")
        store = SessionStore(db_path)

        store.create_session("orig", title="Important Chat")
        store.save_message("orig", "user", "hi")

        forked = Session.fork("orig", store)

        assert forked is not None
        assert forked.title == "Important Chat"

    def test_fork_with_custom_title(self, tmp_path):
        """Fork with a custom title overrides the original title."""
        db_path = str(tmp_path / "fork_custom.db")
        store = SessionStore(db_path)

        store.create_session("orig", title="Original Title")
        store.save_message("orig", "user", "hi")

        forked = Session.fork("orig", store, title="Forked Title")

        assert forked is not None
        assert forked.title == "Forked Title"

        # Verify the original title is unchanged
        orig = Session.load("orig", store)
        assert orig is not None
        assert orig.title == "Original Title"

    def test_fork_nonexistent_returns_none(self, tmp_path):
        """Fork of a nonexistent session returns None."""
        db_path = str(tmp_path / "fork_none.db")
        store = SessionStore(db_path)

        result = Session.fork("does-not-exist", store)

        assert result is None
