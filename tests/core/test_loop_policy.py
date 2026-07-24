"""LoopPolicy 单测"""

import pytest

from merco.core.loop_policy import DefaultLoopPolicy, LoopDecision, LoopPolicy, LoopPolicyRegistry, LoopState


class AlwaysContinuePolicy(LoopPolicy):
    name = "always_continue"

    async def decide(self, response, state):
        return LoopDecision(action="continue", reason="test")


def test_loop_state_creation():
    """LoopState 创建"""
    state = LoopState(
        iteration=1,
        tool_calls_count=2,
        max_tool_calls=10,
        has_tool_calls=True,
        finish_reason="tool_calls",
    )
    assert state.iteration == 1
    assert state.has_tool_calls is True


def test_loop_decision_creation():
    """LoopDecision 创建"""
    d = LoopDecision(action="exit", reason="done")
    assert d.action == "exit"
    assert d.reason == "done"


def test_loop_policy_abc():
    """LoopPolicy 抽象类不能直接实例化"""
    with pytest.raises(TypeError):
        LoopPolicy()  # noqa


@pytest.mark.asyncio
async def test_default_policy_continue_on_tool_calls():
    """默认策略：有 tool_calls → continue"""
    p = DefaultLoopPolicy()
    state = LoopState(0, 0, 10, has_tool_calls=True)
    d = await p.decide({"tool_calls": [{"name": "echo"}]}, state)
    assert d.action == "continue"


@pytest.mark.asyncio
async def test_default_policy_exit_without_tool_calls():
    """默认策略：无 tool_calls → exit"""
    p = DefaultLoopPolicy()
    state = LoopState(0, 0, 10, has_tool_calls=False)
    d = await p.decide({"content": "done"}, state)
    assert d.action == "exit"


def test_registry_register_get_active():
    """Registry 注册/获取/激活"""
    reg = LoopPolicyRegistry()
    default = DefaultLoopPolicy()
    custom = AlwaysContinuePolicy()
    reg.register(default)
    reg.register(custom)
    assert reg.get("default") is default
    reg.set_active("always_continue")
    assert reg.active is custom


def test_registry_set_missing_raises():
    """set_active 未注册策略抛 KeyError"""
    reg = LoopPolicyRegistry()
    reg.register(DefaultLoopPolicy())
    with pytest.raises(KeyError):
        reg.set_active("missing")
