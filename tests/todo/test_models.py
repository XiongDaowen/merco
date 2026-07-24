"""TodoItem 数据模型单测"""

from merco.todo.models import TodoItem


def test_todo_item_creation():
    """TodoItem 默认值正确"""
    item = TodoItem(id="t1", title="测试任务")
    assert item.id == "t1"
    assert item.title == "测试任务"
    assert item.description == ""
    assert item.status == "pending"
    assert item.priority == 1
    assert item.parent_id is None
    assert item.assigned_to is None
    assert item.result == ""


def test_todo_item_with_values():
    """TodoItem 自定义值"""
    item = TodoItem(
        id="t2",
        title="高优先级",
        description="详细描述",
        status="in_progress",
        priority=2,
        parent_id="t1",
        assigned_to="sub_agent_1",
        created_at="2026-06-20T00:00:00",
        updated_at="2026-06-20T00:00:00",
        result="部分结果",
    )
    assert item.priority == 2
    assert item.parent_id == "t1"
    assert item.assigned_to == "sub_agent_1"
