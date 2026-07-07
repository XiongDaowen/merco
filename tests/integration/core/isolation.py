"""全隔离服务工厂 — 每个测试场景独立的状态服务"""
import pytest
from pathlib import Path

from merco.sandbox import snapshot
from merco.scheduler.cron import CronScheduler
from merco.sandbox.guard import ToolGuard
from merco.skills.registry import SkillRegistry


@pytest.fixture
def isolation_services(tmp_path, monkeypatch):
    """为每个场景创建独立的有状态服务"""
    # 1. 快照 → tmp_path/snapshots/
    snapshot_root = tmp_path / "snapshots"
    monkeypatch.setattr(snapshot, "SNAPSHOT_DIR", snapshot_root)

    # 2. Todo → tmp_path/todos.db
    todo_db = tmp_path / "todos.db"

    # 3. 调度器 → 独立实例
    scheduler = CronScheduler()

    # 4. Guard → 独立实例
    guard = ToolGuard()

    # 5. SkillRegistry → 独立实例
    skill_registry = SkillRegistry()

    return {
        "snapshot_root": snapshot_root,
        "todo_db": todo_db,
        "scheduler": scheduler,
        "guard": guard,
        "skill_registry": skill_registry,
    }