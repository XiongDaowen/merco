"""TodoItem 数据模型"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class TodoItem:
    """任务项"""

    id: str
    title: str
    description: str = ""
    status: str = "pending"  # pending / in_progress / completed / failed
    priority: int = 1  # 0=低 1=中 2=高
    parent_id: str | None = None
    assigned_to: str | None = None
    created_at: str = ""
    updated_at: str = ""
    result: str = ""
