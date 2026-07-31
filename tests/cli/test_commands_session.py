"""测试 /fork、/sessions、/report 的摘要触发与 token 展示"""

import pytest

from cli.commands import cmd_fork, cmd_sessions, cmd_report
from tests.conftest import MockModelProvider


@pytest.mark.asyncio
async def test_fork_writes_summary_to_new_session(test_agent):
    """fork 时总结当前会话，写入新 fork 的 metadata"""
    # 给当前会话足够消息（>= min_messages=8）
    for i in range(10):
        test_agent.session.add_message("user", f"msg {i}")
        test_agent.session.add_message("assistant", f"reply {i}")
    test_agent.session.save()
    test_agent._session_store.save_metadata(test_agent.session.id, test_agent.session.metadata)

    # 摘要 LLM 调用返回固定摘要
    test_agent.provider = MockModelProvider([{"content": "目标: fork 测试"}])

    await cmd_fork(test_agent, "")

    # 新 session 的 metadata 应有 context_summary
    new_id = test_agent.session.id
    sdata = test_agent._session_store.load_session(new_id)
    assert sdata["metadata"].get("context_summary") == "目标: fork 测试"


@pytest.mark.asyncio
async def test_fork_skips_summary_when_disabled(test_agent):
    """session_summarize=False 时不生成摘要"""
    test_agent.config.session_summarize = False
    for i in range(10):
        test_agent.session.add_message("user", f"msg {i}")
        test_agent.session.add_message("assistant", f"reply {i}")
    test_agent.session.save()
    test_agent._session_store.save_metadata(test_agent.session.id, test_agent.session.metadata)

    test_agent.provider = MockModelProvider([{"content": "should not be called"}])
    await cmd_fork(test_agent, "")

    new_id = test_agent.session.id
    sdata = test_agent._session_store.load_session(new_id)
    assert "context_summary" not in sdata["metadata"]


@pytest.mark.asyncio
async def test_switch_writes_summary_to_left_session(test_agent):
    """切换会话时总结被离开的会话，写入其 metadata"""
    # 当前会话有足够消息
    for i in range(10):
        test_agent.session.add_message("user", f"msg {i}")
        test_agent.session.add_message("assistant", f"reply {i}")
    test_agent.session.save()
    left_id = test_agent.session.id
    test_agent._session_store.save_metadata(left_id, test_agent.session.metadata)

    # 造一个目标会话
    from merco.core.session import Session

    target = Session(store=test_agent._session_store)
    test_agent._session_store.create_session(target.id)
    target.save()

    # 摘要 LLM 调用
    test_agent.provider = MockModelProvider([{"content": "目标: 切换测试"}])

    await cmd_sessions(test_agent, target.id)

    # 被离开的会话 metadata 应有摘要
    left_data = test_agent._session_store.load_session(left_id)
    assert left_data["metadata"].get("context_summary") == "目标: 切换测试"
    # 当前已切到目标
    assert test_agent.session.id == target.id


@pytest.mark.asyncio
async def test_switch_skips_summary_when_disabled(test_agent):
    """session_summarize=False 时切换不生成摘要"""
    test_agent.config.session_summarize = False
    for i in range(10):
        test_agent.session.add_message("user", f"msg {i}")
        test_agent.session.add_message("assistant", f"reply {i}")
    test_agent.session.save()
    left_id = test_agent.session.id
    test_agent._session_store.save_metadata(left_id, test_agent.session.metadata)

    from merco.core.session import Session

    target = Session(store=test_agent._session_store)
    test_agent._session_store.create_session(target.id)
    target.save()

    test_agent.provider = MockModelProvider([{"content": "should not be called"}])
    await cmd_sessions(test_agent, target.id)

    left_data = test_agent._session_store.load_session(left_id)
    assert "context_summary" not in left_data["metadata"]
