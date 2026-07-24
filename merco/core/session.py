"""会话管理"""

import logging
import uuid

_logger = logging.getLogger("merco.session")


class Session:
    """单次对话会话 — 数据容器，对接 SessionStore 持久化"""

    def __init__(self, session_id: str = None, title: str = "", store=None):
        self.id = session_id or _new_id()
        self.title = title
        self.messages: list[dict] = []
        self.metadata: dict = {}
        self._store = store
        self._dirty = False  # 有未持久化的消息

    # ── 消息 ──────────────────────────────────────────────

    def add_message(self, role: str, content: str, **kwargs):
        """添加消息。不立即写磁盘（由 agent 循环结束时统一 save）"""
        r = kwargs.get("reasoning", "")
        if r:
            _logger.debug("add_message(%s): reasoning=%d chars, content=%d chars", role, len(r), len(content))
        msg = {"role": role, "content": content}
        msg.update(kwargs)
        self.messages.append(msg)
        self._dirty = True

    def get_history(self) -> list[dict]:
        return self.messages.copy()

    # ── 持久化 ────────────────────────────────────────────

    def save(self):
        """将未持久化的消息写入 SQLite。增量：DB 已有 N 条，只写 messages[N:]"""
        if not self._store or not self._dirty:
            return

        self._store.create_session(self.id, self.title)

        existing = self._store.count_messages(self.id)
        for msg in self.messages[existing:]:
            self._store.save_message(
                session_id=self.id,
                role=msg.get("role", ""),
                content=msg.get("content", ""),
                tool_call_id=msg.get("tool_call_id", ""),
                tool_calls=msg.get("tool_calls"),
                reasoning=msg.get("reasoning", ""),
            )
        self._dirty = False

    def delete(self):
        if self._store:
            self._store.delete_session(self.id)

    # ── 工厂 ──────────────────────────────────────────────

    @classmethod
    def load(cls, session_id: str, store) -> "Session | None":
        """从 store 加载完整会话（含历史消息）"""
        data = store.load_session(session_id)
        if not data:
            return None

        s = cls(session_id=data["id"], title=data["title"], store=store)
        s.messages = data["messages"]
        s.metadata = data.get("metadata", {})
        s._dirty = False
        return s

    @classmethod
    def fork(cls, session_id: str, store, title: str = None) -> "Session | None":
        """从 session_id 克隆新会话。返回新 Session 或 None。"""
        try:
            new_id = store.clone_session(session_id)
        except ValueError:
            return None
        if title is not None:
            store.set_title(new_id, title)
        return cls.load(new_id, store)

    @classmethod
    def resume_or_create(cls, store, session_id: str = None) -> "Session":
        """恢复指定会话，或自动恢复上次，或新建"""
        if session_id:
            s = cls.load(session_id, store)
            if s:
                return s
        # 自动恢复上次会话
        recent = store.list_sessions(limit=1)
        if recent:
            s = cls.load(recent[0]["id"], store)
            if s:
                return s
        # 新建
        s = cls(store=store)
        store.create_session(s.id)
        return s


def _new_id() -> str:
    return str(uuid.uuid4())[:8]
