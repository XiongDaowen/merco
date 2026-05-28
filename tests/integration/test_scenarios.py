"""Agent 核心循环集成测试 — Scenario 模式

每个测试 = 声明 LLM 响应 → 执行 → 验证
"""

import pytest
from merco.core.session import Session
from merco.sandbox.guard import ToolGuard
from tests.conftest import MockLLMClient


# ═══════════════════════════════════════════════════════════
# 基础对话
# ═══════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_simple_conversation(test_agent):
    """用户问 → LLM 答 → session 有 2 条消息"""
    test_agent.llm = MockLLMClient([{"content": "你好！"}])

    result = await test_agent.run("你好")
    assert result == "你好！"
    assert len(test_agent.session.messages) == 2
    assert test_agent.session.messages[0]["role"] == "user"
    assert test_agent.session.messages[1]["role"] == "assistant"


@pytest.mark.asyncio
async def test_multi_turn(test_agent):
    """多轮对话 → session 累积消息"""
    test_agent.llm = MockLLMClient([
        {"content": "第一轮"},
        {"content": "第二轮"},
    ])

    r1 = await test_agent.run("问1")
    r2 = await test_agent.run("问2")
    assert r1 == "第一轮"
    assert r2 == "第二轮"
    assert len(test_agent.session.messages) == 4  # user+asst × 2


# ═══════════════════════════════════════════════════════════
# 工具调用
# ═══════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_tool_call_chain(test_agent):
    """用户问 → tool_call → tool_result → LLM 答 → 完整链路持久化"""
    test_agent.llm = MockLLMClient([
        {
            "tool_calls": [{"id": "t1", "name": "echo",
                            "arguments": {"message": "hello"}}],
        },
        {"content": "工具返回了 hello"},
    ])

    result = await test_agent.run("回显hello")
    assert "工具返回了 hello" in result
    msgs = test_agent.session.messages
    assert len(msgs) == 4  # user + asst(tool_call) + tool + asst
    assert msgs[1]["role"] == "assistant"
    assert msgs[1].get("tool_calls") is not None  # 含 tool_calls
    assert msgs[2]["role"] == "tool"


# ═══════════════════════════════════════════════════════════
# Session 持久化
# ═══════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_session_save_and_load(test_agent):
    """run → save → 新 session load → 消息一致"""
    test_agent.llm = MockLLMClient([{"content": "你好！"}])

    await test_agent.run("你好")
    test_agent.session.save()

    # 新建 session 从 store 加载
    s2 = Session.load(test_agent.session.id, test_agent._session_store)
    assert s2 is not None
    assert len(s2.messages) == 2
    assert s2.messages[0]["role"] == "user"
    assert s2.messages[0]["content"] == "你好"
    assert s2.messages[1]["role"] == "assistant"


@pytest.mark.asyncio
async def test_session_resume_or_create(test_agent):
    """resume_or_create → 自动恢复上次会话"""
    test_agent.llm = MockLLMClient([{"content": "第一条"}])
    await test_agent.run("问")
    test_agent.session.save()

    s = Session.resume_or_create(test_agent._session_store)
    assert s.id == test_agent.session.id
    assert len(s.messages) == 2


@pytest.mark.asyncio
async def test_new_session_preserves_old(test_agent):
    """/new → 旧 session 保留 → 新 session 独立"""
    test_agent.llm = MockLLMClient([
        {"content": "旧对话"}, {"content": "新对话"},
    ])

    await test_agent.run("旧问题")
    old_id = test_agent.session.id
    test_agent.session.save()

    # /new
    test_agent.reset()
    await test_agent.run("新问题")

    assert test_agent.session.id != old_id
    sessions = test_agent._session_store.list_sessions()
    assert len(sessions) == 2  # 两个 session 都在


# ═══════════════════════════════════════════════════════════
# Guard 守卫
# ═══════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_guard_sensitive_blocked(test_agent):
    """sandbox_mode=ask → bash rm → 拦截"""
    test_agent.config.sandbox_mode = "ask"
    test_agent.guard = ToolGuard(mode="ask")

    # mock confirm 返回拒绝
    async def mock_reject(self, command, rule):
        return False
    ToolGuard._confirm = mock_reject

    result = await test_agent.guard.check("bash", {"command": "rm file.txt"})
    assert result is False


@pytest.mark.asyncio
async def test_guard_normal_passes(test_agent):
    """sandbox_mode=ask → bash ls → 放行"""
    test_agent.config.sandbox_mode = "ask"
    test_agent.guard = ToolGuard(mode="ask")

    result = await test_agent.guard.check("bash", {"command": "ls -la"})
    assert result is True


@pytest.mark.asyncio
async def test_guard_auto_skips(test_agent):
    """sandbox_mode=auto → 守卫全跳过"""
    test_agent.config.sandbox_mode = "auto"
    test_agent.guard = ToolGuard(mode="auto")

    result = await test_agent.guard.check("bash", {"command": "rm -rf /"})
    assert result is True


# ═══════════════════════════════════════════════════════════
# Context 恢复
# ═══════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_context_restore_after_switch(test_agent):
    """/sessions 切换 → 清旧 context → 灌入新 session 消息"""
    test_agent.llm = MockLLMClient([{"content": "会话A"}])
    await test_agent.run("会话A的问题")
    id_a = test_agent.session.id
    test_agent.session.save()

    # 模拟切到会话 A
    s_a = Session.load(id_a, test_agent._session_store)
    test_agent.session = s_a
    test_agent._restore_context()

    # context 中应有会话 A 的消息
    msgs = test_agent.context.messages
    assert len(msgs) == 2
    assert msgs[0]["role"] == "user"
    assert msgs[0]["content"] == "会话A的问题"
