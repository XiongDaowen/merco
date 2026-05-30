"""SQLite 会话持久化存储"""

import json
import logging
import os
import sqlite3
import time
import uuid
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("merco.session_store")


class SessionStore:
    """SQLite 会话存储 — 两张表，自动建表，增量写消息"""

    def __init__(self, db_path: str):
        self.db_path = os.path.expanduser(db_path)
        self._ensure_db()

    # ── 表初始化 ──────────────────────────────────────────

    def _ensure_db(self):
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        with self._conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id            TEXT PRIMARY KEY,
                    title         TEXT DEFAULT '',
                    created_at    TEXT NOT NULL,
                    updated_at    TEXT NOT NULL,
                    message_count INTEGER DEFAULT 0,
                    parent_id     TEXT,
                    metadata      TEXT DEFAULT '{}'
                );

                CREATE TABLE IF NOT EXISTS messages (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id    TEXT NOT NULL,
                    role          TEXT NOT NULL,
                    content       TEXT DEFAULT '',
                    tool_call_id  TEXT DEFAULT '',
                    tool_calls    TEXT DEFAULT '[]',
                    reasoning     TEXT DEFAULT '',
                    timestamp     TEXT NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES sessions(id)
                );

                CREATE INDEX IF NOT EXISTS idx_msg_session
                    ON messages(session_id, id);
            """)
            # 兼容已有数据库：加 metadata 列
            try:
                conn.execute("ALTER TABLE sessions ADD COLUMN metadata TEXT DEFAULT '{}'")
            except Exception:
                pass  # 列已存在

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.row_factory = sqlite3.Row
        return conn

    # ── Session CRUD ──────────────────────────────────────

    def create_session(self, session_id: str, title: str = "") -> dict:
        now = _now()
        with self._conn() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO sessions (id, title, created_at, updated_at) "
                "VALUES (?, ?, ?, ?)",
                (session_id, title or "", now, now),
            )
            conn.commit()
        return {"id": session_id, "title": title, "created_at": now}

    def save_message(self, session_id: str, role: str, content: str = "",
                     tool_call_id: str = "", tool_calls: list | None = None,
                     reasoning: str = "") -> int:
        now = _now()
        tc_json = json.dumps(tool_calls or [], ensure_ascii=False)
        with self._conn() as conn:
            cur = conn.execute(
                "INSERT INTO messages (session_id, role, content, tool_call_id, "
                "tool_calls, reasoning, timestamp) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (session_id, role, content, tool_call_id, tc_json, reasoning, now),
            )
            conn.execute(
                "UPDATE sessions SET updated_at = ?, "
                "message_count = message_count + 1 "
                "WHERE id = ?",
                (now, session_id),
            )
            conn.commit()
            return cur.lastrowid

    def load_session(self, session_id: str) -> dict | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM sessions WHERE id = ?", (session_id,)
            ).fetchone()
            if not row:
                return None

            messages = conn.execute(
                "SELECT * FROM messages WHERE session_id = ? ORDER BY id",
                (session_id,),
            ).fetchall()

        return {
            "id": row["id"],
            "title": row["title"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "message_count": row["message_count"],
            "parent_id": row["parent_id"],
            "metadata": json.loads(row["metadata"] or "{}"),
            "messages": [
                {
                    "role": m["role"],
                    "content": m["content"],
                    "tool_call_id": m["tool_call_id"],
                    "tool_calls": json.loads(m["tool_calls"]),
                    "reasoning": m["reasoning"],
                    "timestamp": m["timestamp"],
                }
                for m in messages
            ],
        }

    def list_sessions(self, limit: int = 20) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT id, title, created_at, updated_at, message_count "
                "FROM sessions ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def count_messages(self, session_id: str) -> int:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT COUNT(*) as cnt FROM messages WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            return row["cnt"] if row else 0

    def save_metadata(self, session_id: str, metadata: dict):
        import json
        with self._conn() as conn:
            conn.execute(
                "UPDATE sessions SET metadata = ? WHERE id = ?",
                (json.dumps(metadata, ensure_ascii=False), session_id),
            )
            conn.commit()

    def update_title(self, session_id: str, title: str):
        with self._conn() as conn:
            conn.execute(
                "UPDATE sessions SET title = ? WHERE id = ? AND title = ''",
                (title, session_id),
            )
            conn.commit()

    def set_title(self, session_id: str, title: str) -> bool:
        """Always set the title, regardless of current value. Returns True if a row was updated."""
        with self._conn() as conn:
            cur = conn.execute(
                "UPDATE sessions SET title = ?, updated_at = ? WHERE id = ?",
                (title, _now(), session_id),
            )
            conn.commit()
            return cur.rowcount > 0

    def delete_session(self, session_id: str):
        with self._conn() as conn:
            conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
            conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
            conn.commit()

    def clone_session(self, session_id: str) -> str:
        """Clone a session and all its messages to a new session ID.

        Returns the new session ID (uuid4 hex string).
        Raises ValueError if the original session does not exist.
        """
        original = self.load_session(session_id)
        if original is None:
            raise ValueError(f"Session not found: {session_id}")

        new_id = uuid.uuid4().hex
        now = _now()

        with self._conn() as conn:
            conn.execute(
                "INSERT INTO sessions (id, title, created_at, updated_at, "
                "message_count, parent_id, metadata) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    new_id,
                    original["title"],
                    now,
                    now,
                    0,  # updated atomically after message copies
                    session_id,
                    json.dumps(original["metadata"], ensure_ascii=False),
                ),
            )

            for msg in original["messages"]:
                tc_json = json.dumps(msg.get("tool_calls") or [], ensure_ascii=False)
                conn.execute(
                    "INSERT INTO messages (session_id, role, content, "
                    "tool_call_id, tool_calls, reasoning, timestamp) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        new_id,
                        msg["role"],
                        msg.get("content", ""),
                        msg.get("tool_call_id", ""),
                        tc_json,
                        msg.get("reasoning", ""),
                        now,
                    ),
                )

            # Update message_count atomically
            conn.execute(
                "UPDATE sessions SET message_count = ("
                "SELECT COUNT(*) FROM messages WHERE session_id = ?"
                ") WHERE id = ?",
                (new_id, new_id),
            )
            conn.commit()

        return new_id


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")
