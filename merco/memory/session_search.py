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
                "INSERT INTO messages_fts(rowid, content, session_id) "
                "SELECT id, content, session_id FROM messages"
            )
            logger.info("FTS index rebuilt")

    def search(self, query: str, session_id: str | None = None,
               limit: int = 20) -> list[dict]:
        """搜索消息，返回排序结果 + 片段"""
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
        params = [self._sanitize(query)]

        if session_id:
            sql += " AND m.session_id = ?"
            params.append(session_id)

        sql += " ORDER BY rank LIMIT ?"
        params.append(limit)

        with self._conn() as conn:
            rows = conn.execute(sql, params).fetchall()

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
        """清洗 FTS5 查询——去特殊字符，加前缀匹配。FTS5 中 `-` 开头表示 NOT/列约束，`.` 和 `/` 破坏分词。"""
        q = query.strip()
        # 去掉 FTS5 危险字符：引号、运算符、路径分隔符、括号等。只保留字母/数字/下划线/中文。
        q = re.sub(r'[^\w\s\u4e00-\u9fff]', ' ', q, flags=re.UNICODE)
        # 合并多余空格，提取有效词
        terms = [t for t in q.split() if t]  # 只去空串，保留所有有效词（FTS5 自行处理 min token）
        if not terms:
            return "*"
        return " ".join(t + "*" for t in terms)
