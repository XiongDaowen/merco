"""SubAgentManager 单测"""

from unittest.mock import AsyncMock, MagicMock

import pytest


class TestSubAgentManager:
    @pytest.mark.asyncio
    async def test_create_sub_agent(self, test_agent):
        """创建子代理继承父配置"""
        from merco.agents.subagent import SubAgentManager

        manager = SubAgentManager(test_agent)
        sub_agent = await manager._create_sub_agent("default")

        # 继承父的 config
        assert sub_agent.config == test_agent.config
        # 继承父的 tool_registry
        assert sub_agent.tool_registry == test_agent.tool_registry
        # 隔离 session
        assert sub_agent.session.id != test_agent.session.id

    @pytest.mark.asyncio
    async def test_dispatch_updates_todo(self, test_agent):
        """派发子代理更新 Todo 状态"""
        import tempfile

        from merco.agents.subagent import SubAgentManager
        from merco.todo.manager import TodoManager

        with tempfile.TemporaryDirectory() as td:
            todo_manager = TodoManager(f"{td}/todos.db")
            test_agent.todo_manager = todo_manager

            manager = SubAgentManager(test_agent)
            todo = todo_manager.create("测试任务")

            # Mock 子代理执行
            mock_result = "子代理完成"
            manager._create_sub_agent = AsyncMock(
                return_value=MagicMock(
                    session=MagicMock(id="sub_1"),
                    run=AsyncMock(return_value=mock_result),
                )
            )

            await manager.dispatch(todo.id, "执行任务")

            # 验证 Todo 更新
            updated = todo_manager.get(todo.id)
            assert updated.status == "completed"
            assert updated.result == mock_result
            assert updated.assigned_to == "sub_1"
