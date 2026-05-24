"""记忆搜索索引"""

import sqlite3
from pathlib import Path


class MemorySearch:
    """基于 SQLite FTS5 的记忆搜索"""

    def __init__(self, db_path: str = None):
        self.db_path = Path(db_path or "~/.merco/memory.db").expanduser()
        self._init_db()

    def _init_db(self):
        """初始化数据库"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS memories USING fts5(
                    key, content, tags
                )
            """)

    def index(self, key: str, content: str, tags: str = ""):
        """索引记忆内容"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("INSERT INTO memories VALUES (?, ?, ?)", (key, content, tags))

    def search(self, query: str, limit: int = 10) -> list[dict]:
        """搜索记忆"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT key, content, tags FROM memories WHERE memories MATCH ? LIMIT ?",
                (query, limit),
            )
            return [{"key": row[0], "content": row[1], "tags": row[2]} for row in cursor.fetchall()]
