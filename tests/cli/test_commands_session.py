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
