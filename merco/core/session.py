"""会话管理"""


class Session:
    """管理单次对话会话"""

    def __init__(self, session_id: str = None):
        self.id = session_id or self._generate_id()
        self.messages = []
        self.metadata = {}

    def add_message(self, role: str, content: str):
        """添加消息到会话"""
        self.messages.append({"role": role, "content": content})

    def get_history(self) -> list:
        """获取会话历史"""
        return self.messages.copy()

    def compact(self, strategy: str = "summary"):
        """压缩会话上下文"""
        raise NotImplementedError

    @staticmethod
    def _generate_id() -> str:
        import uuid
        return str(uuid.uuid4())[:8]


class SessionStore:
    """会话持久化存储"""

    def __init__(self, db_path: str = None):
        self.db_path = db_path or "~/.merco/sessions.db"

    def save(self, session: Session):
        """保存会话"""
        raise NotImplementedError

    def load(self, session_id: str) -> Session:
        """加载会话"""
        raise NotImplementedError

    def list_sessions(self) -> list:
        """列出所有会话"""
        raise NotImplementedError
