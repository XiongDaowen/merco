"""任务管理"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from enum import Enum


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class Task:
    """任务对象"""
    id: str
    name: str
    description: str
    status: TaskStatus = TaskStatus.PENDING
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result: Optional[str] = None
    error: Optional[str] = None


class TaskManager:
    """任务管理器"""

    def __init__(self):
        self._tasks: dict[str, Task] = {}

    def create(self, name: str, description: str) -> Task:
        """创建任务"""
        import uuid
        task = Task(id=str(uuid.uuid4())[:8], name=name, description=description)
        self._tasks[task.id] = task
        return task

    def get(self, task_id: str) -> Optional[Task]:
        """获取任务"""
        return self._tasks.get(task_id)

    def update_status(self, task_id: str, status: TaskStatus, result: str = None, error: str = None):
        """更新任务状态"""
        task = self._tasks.get(task_id)
        if task:
            task.status = status
            task.result = result
            task.error = error
            if status == TaskStatus.RUNNING:
                task.started_at = datetime.now()
            elif status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
                task.completed_at = datetime.now()

    def list_tasks(self, status: TaskStatus = None) -> list[Task]:
        """列出任务"""
        tasks = list(self._tasks.values())
        if status:
            tasks = [t for t in tasks if t.status == status]
        return tasks
