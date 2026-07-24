"""会话管理测试"""

from merco.core.session import Session


class TestSession:
    def test_create_session(self):
        session = Session()
        assert session.id is not None
        assert len(session.messages) == 0

    def test_add_message(self):
        session = Session()
        session.add_message("user", "Hello")
        assert len(session.messages) == 1
        assert session.messages[0]["role"] == "user"

    def test_get_history(self):
        session = Session()
        session.add_message("user", "Hello")
        session.add_message("assistant", "Hi!")
        history = session.get_history()
        assert len(history) == 2
