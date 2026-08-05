"""Session.add_message / save 透传 usage 测试"""

import pytest

from merco.core.session import Session


class FakeStore:
    """记录 save_message 调用的假 store"""

    def __init__(self):
        self.saved = []

    def create_session(self, session_id, title=""):
        pass

    def count_messages(self, session_id):
        return 0

    def save_message(self, session_id, role, content="", tool_call_id="", tool_calls=None, reasoning="", usage=None):
        self.saved.append({"role": role, "usage": usage})


@pytest.mark.asyncio
async def test_add_message_stores_usage_on_dict():
    s = Session(session_id="s1", store=FakeStore())
    s.add_message("assistant", "hi", usage={"tokens_in": 10, "tokens_out": 5, "cached_tokens": 0})
    assert s.messages[0]["usage"] == {"tokens_in": 10, "tokens_out": 5, "cached_tokens": 0}


def test_save_passes_usage_to_store():
    store = FakeStore()
    s = Session(session_id="s1", store=store)
    s.add_message("assistant", "hi", usage={"tokens_in": 10, "tokens_out": 5, "cached_tokens": 0})
    s.save()
    assert store.saved[0]["usage"] == {"tokens_in": 10, "tokens_out": 5, "cached_tokens": 0}


def test_save_passes_none_usage_when_absent():
    store = FakeStore()
    s = Session(session_id="s1", store=store)
    s.add_message("user", "hi")  # 无 usage
    s.save()
    assert store.saved[0]["usage"] is None
