"""TodoManager — SQLite 任务管理"""

from __future__ import annotations

import os
import sqlite3
import uuid
from datetime import datetime

from .models import TodoItem


class TodoManager:
    """Todo 任务管理器"""

    def __init__(self, db_path: str):
        self.db_path = os.path.expanduser(db_path)
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS todos (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    description TEXT DEFAULT '',
                    status TEXT DEFAULT 'pending',
                    priority INTEGER DEFAULT 1,
                    parent_id TEXT,
                    assigned_to TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    result TEXT DEFAULT ''
                )
            """)

    def create(self, title: str, description: str = "", priority: int = 1, parent_id: str = None) -> TodoItem:
        """创建任务"""
        now = datetime.now().isoformat()
        item = TodoItem(
            id=str(uuid.uuid4()),
            title=title,
            description=description,
            priority=priority,
            parent_id=parent_id,
            created_at=now,
            updated_at=now,
        )
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO todos VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    item.id,
                    item.title,
                    item.description,
                    item.status,
                    item.priority,
                    item.parent_id,
                    item.assigned_to,
                    item.created_at,
                    item.updated_at,
                    item.result,
                ),
            )
        return item

    def get(self, id: str) -> TodoItem | None:
        """获取任务"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM todos WHERE id = ?", (id,)).fetchone()
            if not row:
                return None
            return self._row_to_item(row)

    def update(self, id: str, **kwargs) -> TodoItem | None:
        """更新任务"""
        item = self.get(id)
        if not item:
            return None
        kwargs["updated_at"] = datetime.now().isoformat()
        set_clause = ", ".join(f"{k} = ?" for k in kwargs)
        values = list(kwargs.values()) + [id]
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(f"UPDATE todos SET {set_clause} WHERE id = ?", values)
        return self.get(id)

    def list(self, status: str = None, parent_id: str = None) -> list[TodoItem]:
        """列出任务"""
        query = "SELECT * FROM todos WHERE 1=1"
        params = []
        if status:
            query += " AND status = ?"
            params.append(status)
        if parent_id:
            query += " AND parent_id = ?"
            params.append(parent_id)
        query += " ORDER BY priority DESC, created_at ASC"
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(query, params).fetchall()
            return [self._row_to_item(row) for row in rows]

    def delete(self, id: str) -> None:
        """删除任务"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM todos WHERE id = ?", (id,))

    @staticmethod
    def _row_to_item(row: sqlite3.Row) -> TodoItem:
        return TodoItem(
            id=row["id"],
            title=row["title"],
            description=row["description"],
            status=row["status"],
            priority=row["priority"],
            parent_id=row["parent_id"],
            assigned_to=row["assigned_to"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            result=row["result"],
        )
