"""LoopPolicy 集成测试"""
import pytest
from merco.core.loop_policy import LoopPolicy, LoopDecision
from tests.conftest import MockModelProvider


class ForceExitPolicy(LoopPolicy):
    """即使有 tool_calls 也强制退出"""
    name = "force_exit"

    async def decide(self, response, state):
        return LoopDecision(action="exit", reason="forced")


@pytest.mark.asyncio
async def test_default_policy_simple_conversation(test_agent):
    """默认策略：无 tool_calls → 正常退出"""
    test_agent.provider = MockModelProvider([{"content": "hello"}])
    result = await test_agent.run("hi")
    assert result == "hello"


@pytest.mark.asyncio
async def test_default_policy_tool_call_continues(test_agent):
    """默认策略：有 tool_calls → 执行工具并继续"""
    test_agent.provider = MockModelProvider([
        {"tool_calls": [{"id": "t1", "name": "echo", "arguments": {"message": "hi"}}]},
        {"content": "done"},
    ])
    result = await test_agent.run("echo hi")
    assert result == "done"
    assert any(m.get("role") == "tool" for m in test_agent.session.messages)


@pytest.mark.asyncio
async def test_custom_policy_can_force_exit(test_agent):
    """自定义策略可影响 loop 决策"""
    test_agent.loop_policies.register(ForceExitPolicy())
    test_agent.loop_policies.set_active("force_exit")
    test_agent.provider = MockModelProvider([
        {"tool_calls": [{"id": "t1", "name": "echo", "arguments": {"message": "hi"}}], "content": "forced exit"},
    ])
    result = await test_agent.run("echo hi")
    # 强制退出，不执行工具
    assert result == "forced exit"
    assert not any(m.get("role") == "tool" for m in test_agent.session.messages)
