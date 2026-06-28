"""Agent 核心循环集成测试 — Scenario 模式

每个测试 = 声明 LLM 响应 → 执行 → 验证
"""

import httpx
import pytest
from merco.core.pipeline import RecoveryPipeline
from merco.core.recovery.wait import WaitRecovery
from merco.core.session import Session
from merco.sandbox.guard import ToolGuard, GuardAction
from openai import APIStatusError
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
    """sandbox_mode=ask → bash rm → 返回 ASK（需要用户确认）"""
    test_agent.config.sandbox_mode = "ask"
    test_agent.guard = ToolGuard(mode="ask")

    result = await test_agent.guard.check("bash", {"command": "rm file.txt"})
    assert result.action == GuardAction.ASK


@pytest.mark.asyncio
async def test_guard_normal_passes(test_agent):
    """sandbox_mode=ask → bash ls → 放行"""
    test_agent.config.sandbox_mode = "ask"
    test_agent.guard = ToolGuard(mode="ask")

    result = await test_agent.guard.check("bash", {"command": "ls -la"})
    assert result.action == GuardAction.ALLOW


@pytest.mark.asyncio
async def test_guard_auto_skips(test_agent):
    """sandbox_mode=auto → 守卫全跳过"""
    test_agent.config.sandbox_mode = "auto"
    test_agent.guard = ToolGuard(mode="auto")

    result = await test_agent.guard.check("bash", {"command": "rm -rf /"})
    assert result.action == GuardAction.ALLOW


# ═══════════════════════════════════════════════════════════
# Context 压缩
# ═══════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_context_compression_triggered(test_agent):
    """MockLLM 产生 N 条大消息 → context 超过阈值 → 压缩 → messages 变少"""
    # 构造大上下文：每条 ~22000 chars，确保 4 轮后超过 0.8 × 20000 token 阈值
    # (needs_compression 触发条件为 total_tokens > max_tokens × 0.8 = 16000)
    big_msg = "x" * 22000
    test_agent.config.max_input_tokens = 20000
    test_agent.context.max_tokens = 20000  # ContextManager 已在 __init__ 创建，需同步更新

    # Mock LLM 5 次调用：前 4 轮大消息触发压缩，第 5 轮压缩后的正常消息
    test_agent.llm = MockLLMClient([
        {"content": big_msg},  # 第 1 轮
        {"content": big_msg},  # 第 2 轮
        {"content": big_msg},  # 第 3 轮
        {"content": big_msg},  # 第 4 轮 — 累积到 > 16000 tokens，触发压缩
        {"content": "压缩后继续"},  # 压缩后第 5 轮
    ])

    # 跑 4 轮
    for i in range(4):
        await test_agent.run(f"msg {i}")

    # 验证：context.messages 已被压缩（小于 4 轮的 8 条）
    assert len(test_agent.context.messages) < 8

    # 验证：session 持久化了所有消息
    test_agent.session.save()
    loaded = test_agent._session_store.load_session(test_agent.session.id)
    assert len(loaded["messages"]) == 8  # session 完整保存（压缩只在 context 层）


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


# ═══════════════════════════════════════════════════════════
# Session Fork on Compress
# ═══════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_session_fork_on_compress(test_agent):
    """压缩时自动 fork 当前 session 到 child session"""
    # fork_enabled=True / fork_auto_on_compress=True 已是 config 默认值，无需设置
    big_msg = "x" * 22000
    test_agent.config.max_input_tokens = 20000
    test_agent.context.max_tokens = 20000  # ContextManager 已在 __init__ 创建，需同步更新

    # Mock LLM 5 次调用：前 4 轮大消息累积触发压缩 → 自动 fork
    test_agent.llm = MockLLMClient([
        {"content": big_msg},
        {"content": big_msg},
        {"content": big_msg},
        {"content": big_msg},
        {"content": "压缩后继续"},
    ])

    original_session_id = test_agent.session.id

    # 跑 5 轮触发压缩
    for i in range(5):
        await test_agent.run(f"msg {i}")

    # 验证：session store 至少 2 个 session（原 + fork child）
    sessions = test_agent._session_store.list_sessions()
    assert len(sessions) >= 2

    # 验证：fork session 存在且包含原始消息
    children = test_agent._session_store.get_children(original_session_id)
    assert len(children) >= 1
    forked = children[0]
    forked_data = test_agent._session_store.load_session(forked["id"])
    assert len(forked_data["messages"]) > 0


# ═══════════════════════════════════════════════════════════
# MCP tool calling E2E
# ═══════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_mcp_tool_calling_e2e(test_agent, tmp_path):
    """MCP tool 通过 agent.run() 端到端调用 → result 正确"""
    from merco.tools.base import BaseTool

    class MockMCPTool(BaseTool):
        name = "mcp_test_tool"
        description = "MCP test tool"
        toolset = "mcp"
        parameters = {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        }

        async def execute(self, query: str, **kwargs):
            return {"result": f"mcp: {query}"}

    # 把 MCP tool 加入 registry
    test_agent.tool_registry.register(MockMCPTool())

    # Mock LLM：第一次 tool_call → 第二次答
    test_agent.llm = MockLLMClient([
        {
            "tool_calls": [{
                "id": "mcp_t1",
                "name": "mcp_test_tool",
                "arguments": {"query": "test query"},
            }],
        },
        {"content": "MCP 工具返回了结果"},
    ])

    result = await test_agent.run("用 mcp 工具查 test query")
    assert "MCP 工具返回了结果" in result

    # 验证：tool result 注入 session
    msgs = test_agent.session.messages
    assert any(m["role"] == "tool" and "mcp: test query" in str(m.get("content", "")) for m in msgs)

@pytest.mark.asyncio
async def test_recovery_pipeline_retries_on_5xx(test_agent):
    """MockLLM 第一次抛 500 → RecoveryPipeline 重试 → 第二次成功"""
    class FlakyLLM:
        def __init__(self):
            self.calls = 0

        async def chat(self, messages, tools=None, tool_choice="auto"):
            self.calls += 1
            if self.calls == 1:
                # 第一次抛 500 错误
                resp = httpx.Response(500, request=httpx.Request("POST", "http://test"))
                raise APIStatusError("internal server error", response=resp, body=None)
            # 第二次返回成功
            return {"content": "重试后成功", "finish_reason": "stop"}

        async def chat_stream(self, messages, tools=None, tool_choice="auto"):
            resp = await self.chat(messages, tools, tool_choice)
            yield resp

    # 用极短 delay 替换默认 WaitRecovery，避免 3s 真实等待
    test_agent.recovery_pipeline = RecoveryPipeline()
    test_agent.recovery_pipeline.use(WaitRecovery(delay=0.01, max_delay=0.01))
    test_agent.llm = FlakyLLM()

    # 跑一轮：第一次失败 → 重试 → 第二次成功
    result = await test_agent.run("hello")
    assert result == "重试后成功"
    # LLM 至少被调用 2 次（第一次失败 + 重试成功）
    assert test_agent.llm.calls >= 2
