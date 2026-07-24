"""TodoManager 单测"""
import pytest

from merco.todo.manager import TodoManager


@pytest.fixture
def manager(tmp_path):
    return TodoManager(str(tmp_path / "todos.db"))


def test_create_todo(manager):
    """创建任务"""
    item = manager.create("测试任务", "详细描述", priority=2)
    assert item.title == "测试任务"
    assert item.description == "详细描述"
    assert item.priority == 2
    assert item.status == "pending"
    assert item.id  # 自动生成 ID


def test_get_todo(manager):
    """获取任务"""
    item = manager.create("任务1")
    loaded = manager.get(item.id)
    assert loaded.title == "任务1"


def test_update_todo(manager):
    """更新任务"""
    item = manager.create("任务1")
    updated = manager.update(item.id, status="in_progress", result="部分结果")
    assert updated.status == "in_progress"
    assert updated.result == "部分结果"


def test_list_todos(manager):
    """列出任务"""
    manager.create("任务1")
    manager.create("任务2")
    items = manager.list()
    assert len(items) == 2


def test_list_todos_by_status(manager):
    """按状态过滤"""
    manager.create("任务1")
    item2 = manager.create("任务2")
    manager.update(item2.id, status="completed")
    items = manager.list(status="pending")
    assert len(items) == 1
    assert items[0].title == "任务1"


def test_delete_todo(manager):
    """删除任务"""
    item = manager.create("任务1")
    manager.delete(item.id)
    assert manager.get(item.id) is None
