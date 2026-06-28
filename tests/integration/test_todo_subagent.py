"""Todo + SubAgent 端到端集成测试"""
import pytest
from unittest.mock import MagicMock, AsyncMock

from merco.todo.manager import TodoManager
from merco.agents.subagent import SubAgentManager


class TestTodoSubAgentE2E:
    """Todo 创建 -> 派发子代理 -> 结果注入父 context"""

    @pytest.mark.asyncio
    async def test_todo_dispatch_and_result(self, test_agent, tmp_path):
        """完整流程: 创建 Todo -> dispatch -> 状态更新 -> 结果注入"""
        # ── 1. 准备 TodoManager ──
        todo_manager = TodoManager(str(tmp_path / "todos.db"))
        test_agent.todo_manager = todo_manager

        # ── 2. 创建 SubAgentManager ──
        manager = SubAgentManager(test_agent)

        # ── 3. 创建 Todo ──
        todo = todo_manager.create("测试任务", "详细描述")
        assert todo.status == "pending"
        assert todo.title == "测试任务"

        # ── 4. Mock 子代理执行 ──
        mock_result = "子代理完成了任务"
        manager._create_sub_agent = AsyncMock(return_value=MagicMock(
            session=MagicMock(id="sub_1"),
            run=AsyncMock(return_value=mock_result),
        ))

        # ── 5. 派发 ──
        subagent_id = await manager.dispatch(todo.id, "执行任务")

        # ── 6. 验证 Todo 状态 ──
        updated = todo_manager.get(todo.id)
        assert updated.status == "completed"
        assert updated.result == mock_result
        assert updated.assigned_to == "sub_1"

        # ── 7. 验证结果注入父 context ──
        context_messages = test_agent.context.messages
        injected = [m for m in context_messages if "子代理结果" in str(m.get("content", ""))]
        assert len(injected) >= 1, "子代理结果应注入父 context"
        assert todo.id in injected[0]["content"], "注入消息应包含 todo_id"
        assert mock_result in injected[0]["content"], "注入消息应包含执行结果"

    @pytest.mark.asyncio
    async def test_dispatch_failure_marks_todo_failed(self, test_agent, tmp_path):
        """子代理执行失败时 Todo 标记为 failed"""
        todo_manager = TodoManager(str(tmp_path / "todos.db"))
        test_agent.todo_manager = todo_manager

        manager = SubAgentManager(test_agent)
        todo = todo_manager.create("会失败的任务")

        # Mock 子代理执行抛出异常
        manager._create_sub_agent = AsyncMock(return_value=MagicMock(
            session=MagicMock(id="sub_err"),
            run=AsyncMock(side_effect=RuntimeError("boom")),
        ))

        subagent_id = await manager.dispatch(todo.id, "执行会失败")

        # Todo 应标记为 failed
        updated = todo_manager.get(todo.id)
        assert updated.status == "failed"
        assert "boom" in updated.result
        assert updated.assigned_to == "sub_err"

        # 错误结果也应注入父 context
        context_messages = test_agent.context.messages
        injected = [m for m in context_messages if "子代理结果" in str(m.get("content", ""))]
        assert len(injected) >= 1, "错误结果也应注入父 context"
        assert "Error" in injected[0]["content"]

    @pytest.mark.asyncio
    async def test_multiple_dispatches_update_independently(self, test_agent, tmp_path):
        """多次派发，每个 Todo 独立更新"""
        todo_manager = TodoManager(str(tmp_path / "todos.db"))
        test_agent.todo_manager = todo_manager

        manager = SubAgentManager(test_agent)

        todo_a = todo_manager.create("任务 A")
        todo_b = todo_manager.create("任务 B")

        # 按顺序 mock 不同的子代理
        mock_results = ["结果 A", "结果 B"]
        call_count = {"n": 0}

        def make_sub(agent_name="default"):
            idx = call_count["n"]
            call_count["n"] += 1
            return MagicMock(
                session=MagicMock(id=f"sub_{idx}"),
                run=AsyncMock(return_value=mock_results[idx]),
            )

        manager._create_sub_agent = AsyncMock(side_effect=make_sub)

        await manager.dispatch(todo_a.id, "执行 A")
        await manager.dispatch(todo_b.id, "执行 B")

        # 各自独立
        a = todo_manager.get(todo_a.id)
        b = todo_manager.get(todo_b.id)

        assert a.status == "completed"
        assert a.result == "结果 A"
        assert a.assigned_to == "sub_0"

        assert b.status == "completed"
        assert b.result == "结果 B"
        assert b.assigned_to == "sub_1"

    @pytest.mark.asyncio
    async def test_hooks_emit_called(self, test_agent, tmp_path):
        """dispatch 触发 subagent.completed 事件"""
        todo_manager = TodoManager(str(tmp_path / "todos.db"))
        test_agent.todo_manager = todo_manager

        manager = SubAgentManager(test_agent)
        todo = todo_manager.create("事件测试")

        mock_result = "完成"
        manager._create_sub_agent = AsyncMock(return_value=MagicMock(
            session=MagicMock(id="sub_hook"),
            run=AsyncMock(return_value=mock_result),
        ))

        # Patch hooks.emit 以捕获调用
        test_agent.hooks.emit = AsyncMock()

        await manager.dispatch(todo.id, "触发事件")

        test_agent.hooks.emit.assert_called_once_with(
            "subagent.completed", todo_id=todo.id, result=mock_result
        )
