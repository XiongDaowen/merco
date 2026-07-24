"""Session FTS5 全文搜索 — 借鉴 hermes 双 tokenizer 设计

当前: unicode61 tokenizer (英文/Latin 友好)
后期: 加 trigram tokenizer (CJK/子串友好)
"""

import logging
import re

logger = logging.getLogger("merco.session_search")


class SessionSearch:
    """会话全文搜索 — FTS5 索引 + 片段高亮"""

    def __init__(self, store):
        """store: SessionStore 实例，复用其 DB 路径"""
        self._store = store
        self._ensure_index()

    def _conn(self):
        import sqlite3

        conn = sqlite3.connect(self._store.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_index(self):
        with self._conn() as conn:
            conn.executescript("""
                CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts
                    USING fts5(content, tool_name, session_id,
                               content_rowid='id',
                               tokenize='unicode61');

                CREATE TRIGGER IF NOT EXISTS msg_fts_insert
                    AFTER INSERT ON messages BEGIN
                    INSERT INTO messages_fts(rowid, content, tool_name, session_id)
                    VALUES (new.id, new.content, '', new.session_id);
                END;

                CREATE TRIGGER IF NOT EXISTS msg_fts_delete
                    AFTER DELETE ON messages BEGIN
                    INSERT INTO messages_fts(messages_fts, rank)
                    VALUES ('delete', old.id, 1);
                END;
            """)

    def rebuild(self):
        """全量重建 FTS 索引"""
        with self._conn() as conn:
            conn.execute("DELETE FROM messages_fts")
            conn.execute(
                "INSERT INTO messages_fts(rowid, content, session_id) SELECT id, content, session_id FROM messages"
            )
            logger.info("FTS index rebuilt")

    def search(self, query: str, session_id: str | None = None, limit: int = 20) -> list[dict]:
        """搜索消息，返回排序结果 + 片段"""
        import sqlite3

        sanitized = self._sanitize(query)
        sql = """
            SELECT
                m.id, m.session_id, m.role, m.timestamp,
                snippet(messages_fts, 1, '>>>', '<<<', '...', 40) as snippet,
                s.title as session_title
            FROM messages_fts f
            JOIN messages m ON m.id = f.rowid
            JOIN sessions s ON s.id = m.session_id
            WHERE messages_fts MATCH ?
        """
        params = [sanitized]

        if session_id:
            sql += " AND m.session_id = ?"
            params.append(session_id)

        sql += " ORDER BY rank LIMIT ?"
        params.append(limit)

        with self._conn() as conn:
            try:
                rows = conn.execute(sql, params).fetchall()
            except sqlite3.OperationalError:
                # FTS5 syntax error despite sanitization — return empty
                logger.debug("FTS5 query error for: %s", sanitized)
                return []

        return [
            {
                "id": r["id"],
                "session_id": r["session_id"],
                "session_title": r["session_title"],
                "role": r["role"],
                "snippet": r["snippet"],
                "timestamp": r["timestamp"],
            }
            for r in rows
        ]

    @staticmethod
    def _sanitize(query: str) -> str:
        """Port of Hermes's _sanitize_fts5_query — preserve meaning, escape danger.

        Strategy (6 steps):
        1. Protect balanced double-quoted phrases with placeholders
        2. Strip remaining FTS5-special characters (+, {}, (), ", ^)
        3. Normalise wildcard * (collapse repeats, remove leading *)
        4. Remove dangling boolean operators (AND/OR/NOT at start/end)
        5. Wrap hyphenated/dotted/underscored terms as FTS5 phrase literals
        6. Restore preserved quoted phrases
        """
        if not query or not query.strip():
            return "*"

        # Step 1: Extract balanced double-quoted phrases, protect them
        _quoted_parts: list[str] = []

        def _preserve_quoted(m: re.Match) -> str:
            _quoted_parts.append(m.group(0))
            return f"\x00Q{len(_quoted_parts) - 1}\x00"

        sanitized = re.sub(r'"[^"]*"', _preserve_quoted, query)

        # Step 2: Strip remaining FTS5-special characters
        sanitized = re.sub(r"[+{}()\"^]", " ", sanitized)

        # Step 3: Collapse repeated *, remove leading * (prefix needs char before *)
        sanitized = re.sub(r"\*+", "*", sanitized)
        sanitized = re.sub(r"(^|\s)\*", r"\1", sanitized)

        # Step 4: Remove dangling boolean operators at start/end
        sanitized = re.sub(r"(?i)^(AND|OR|NOT)\b\s*", "", sanitized.strip())
        sanitized = re.sub(r"(?i)\s+(AND|OR|NOT)\s*$", "", sanitized.strip())

        # Step 5: Wrap hyphenated/dotted/underscored terms in quotes
        # Single pass avoids double-quoting e.g. my-app.config
        sanitized = re.sub(r"\b(\w+(?:[._-]\w+)+)\b", r'"\1"', sanitized)

        # Step 6: Restore preserved quoted phrases
        for i, quoted in enumerate(_quoted_parts):
            sanitized = sanitized.replace(f"\x00Q{i}\x00", quoted)

        return sanitized.strip() or "*"
