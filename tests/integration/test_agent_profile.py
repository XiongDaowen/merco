"""AgentProfile 端到端集成测试"""

from unittest.mock import AsyncMock, MagicMock

from merco.agents.profile import BUILTIN_PROFILES, AgentProfileRegistry
from merco.agents.subagent import SubAgentManager


async def test_task_tool_dispatches_with_agent_name(test_agent):
    """TaskTool agent=researcher 派发专业子代理"""
    # 用临时目录创建隔离的 TodoManager，agent=researcher 触发 profile-based sub-agent
    reg = AgentProfileRegistry()
    for p in BUILTIN_PROFILES:
        reg.register(p)

    manager = SubAgentManager(test_agent, reg)

    todo = test_agent.todo_manager.create("研究任务")
    mock_result = "研究发现"

    # Mock 子代理执行 — 无真实 LLM
    manager._create_sub_agent = AsyncMock(
        return_value=MagicMock(
            session=MagicMock(id="sub_researcher_1"),
            run=AsyncMock(return_value=mock_result),
        )
    )

    await manager.dispatch(todo.id, "研究某个模块", "researcher")

    updated = test_agent.todo_manager.get(todo.id)
    assert updated.status == "completed"
    assert updated.result == mock_result


async def test_agent_profile_registry_accessible(test_agent):
    """Agent 启动后 agent_profiles registry 有 builtins"""
    profiles = test_agent.agent_profiles.list()
    names = {p.name for p in profiles}
    assert "default" in names
    assert "researcher" in names
    assert "reviewer" in names
    assert "debugger" in names
