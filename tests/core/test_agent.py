"""Tests for Agent recall integration into _build_system_prompt."""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from merco.core.agent import Agent
from merco.core.config import MercoConfig
from merco.memory.recall import RecallResult


class TestBuildSystemPromptRecall:
    """Tests for recall injection in _build_system_prompt."""

    @pytest.mark.asyncio
    async def test_build_system_prompt_is_async(self, test_agent):
        """_build_system_prompt should be a coroutine (async)."""
        agent = test_agent
        assert asyncio.iscoroutinefunction(agent._build_system_prompt)

    @pytest.mark.asyncio
    async def test_build_system_prompt_includes_recall(self, test_agent):
        """When recall returns results, they appear in the system prompt."""
        agent = test_agent
        agent._current_prompt = "how do I test Python?"

        # Mock the recaller to return results
        mock_recaller = MagicMock()
        mock_recaller.recall = AsyncMock(return_value=[
            RecallResult(
                snippet="Used pytest with fixtures",
                session_title="Testing Session",
                score=0.9,
                source="fts5",
            ),
            RecallResult(
                snippet="Mock objects with unittest.mock",
                session_title="Mocking Guide",
                score=0.7,
                source="memory",
            ),
        ])
        agent.recaller = mock_recaller
        agent.config.memory_recall_enabled = True

        prompt = await agent._build_system_prompt()

        assert "相关历史对话" in prompt
        assert "Testing Session" in prompt
        assert "Used pytest with fixtures" in prompt
        assert "Mocking Guide" in prompt
        assert "Mock objects with unittest.mock" in prompt

    @pytest.mark.asyncio
    async def test_build_system_prompt_recall_disabled(self, test_agent):
        """When memory_recall_enabled is False, no recall section injected."""
        agent = test_agent
        agent._current_prompt = "hello"
        agent.config.memory_recall_enabled = False

        mock_recaller = MagicMock()
        mock_recaller.recall = AsyncMock(return_value=[
            RecallResult(snippet="some memory", session_title="T", score=0.5),
        ])
        agent.recaller = mock_recaller

        prompt = await agent._build_system_prompt()

        assert "相关历史对话" not in prompt
        mock_recaller.recall.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_build_system_prompt_no_results(self, test_agent):
        """When recall returns empty list, no recall section injected."""
        agent = test_agent
        agent._current_prompt = "hello"
        agent.config.memory_recall_enabled = True

        mock_recaller = MagicMock()
        mock_recaller.recall = AsyncMock(return_value=[])
        agent.recaller = mock_recaller

        prompt = await agent._build_system_prompt()

        assert "相关历史对话" not in prompt

    @pytest.mark.asyncio
    async def test_build_system_prompt_no_current_prompt(self, test_agent):
        """When _current_prompt is empty, recall is skipped."""
        agent = test_agent
        agent._current_prompt = ""
        agent.config.memory_recall_enabled = True

        mock_recaller = MagicMock()
        mock_recaller.recall = AsyncMock(return_value=[
            RecallResult(snippet="some memory", session_title="T", score=0.5),
        ])
        agent.recaller = mock_recaller

        prompt = await agent._build_system_prompt()

        assert "相关历史对话" not in prompt
        mock_recaller.recall.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_build_system_prompt_recall_error(self, test_agent):
        """If recall raises, it is swallowed and prompt still builds."""
        agent = test_agent
        agent._current_prompt = "hello"
        agent.config.memory_recall_enabled = True

        mock_recaller = MagicMock()
        mock_recaller.recall = AsyncMock(side_effect=RuntimeError("DB down"))
        agent.recaller = mock_recaller

        prompt = await agent._build_system_prompt()

        # Should still return a valid prompt with the base chunks
        assert "Mercury Code" in prompt
        assert "相关历史对话" not in prompt

    @pytest.mark.asyncio
    async def test_build_system_prompt_format(self, test_agent):
        """Verify the recall section formatting."""
        agent = test_agent
        agent._current_prompt = "test"
        agent.config.memory_recall_enabled = True

        mock_recaller = MagicMock()
        mock_recaller.recall = AsyncMock(return_value=[
            RecallResult(
                snippet="First memory snippet",
                session_title="Session One",
                score=0.9,
                source="fts5",
            ),
        ])
        agent.recaller = mock_recaller

        prompt = await agent._build_system_prompt()

        assert "## 相关历史对话（仅供参考）" in prompt
        assert "1. [Session One] First memory snippet" in prompt


class TestCompressAutoFork:
    """Tests for auto-fork on context compress (fork-4)."""

    @pytest.mark.asyncio
    async def test_compress_auto_fork_triggers_clone(self, test_agent):
        """When fork_enabled + fork_auto_on_compress are True, clone_session is called."""
        agent = test_agent
        agent.config.fork_enabled = True
        agent.config.fork_auto_on_compress = True

        # Add a few messages so compressor returns early (len <= 4 → no real compress)
        agent.context.add({"role": "user", "content": "hello"})
        agent.context.add({"role": "assistant", "content": "hi there"})

        with patch.object(agent._session_store, "clone_session", return_value="fake-new-id") as mock_clone:
            await agent._compress_context()
            mock_clone.assert_called_once_with(agent.session.id)

    @pytest.mark.asyncio
    async def test_compress_auto_fork_disabled(self, test_agent):
        """When fork_auto_on_compress=False, clone_session is NOT called."""
        agent = test_agent
        agent.config.fork_enabled = True
        agent.config.fork_auto_on_compress = False

        agent.context.add({"role": "user", "content": "hello"})
        agent.context.add({"role": "assistant", "content": "hi"})

        with patch.object(agent._session_store, "clone_session") as mock_clone:
            await agent._compress_context()
            mock_clone.assert_not_called()

    @pytest.mark.asyncio
    async def test_compress_auto_fork_fork_disabled(self, test_agent):
        """When fork_enabled=False, no auto-fork even if auto_on_compress=True."""
        agent = test_agent
        agent.config.fork_enabled = False
        agent.config.fork_auto_on_compress = True

        agent.context.add({"role": "user", "content": "hello"})
        agent.context.add({"role": "assistant", "content": "hi"})

        with patch.object(agent._session_store, "clone_session") as mock_clone:
            await agent._compress_context()
            mock_clone.assert_not_called()

    @pytest.mark.asyncio
    async def test_compress_auto_fork_clone_failure_does_not_block(self, test_agent):
        """If clone_session raises, compress still completes normally."""
        agent = test_agent
        agent.config.fork_enabled = True
        agent.config.fork_auto_on_compress = True

        agent.context.add({"role": "user", "content": "hello"})
        agent.context.add({"role": "assistant", "content": "hi"})

        with patch.object(agent._session_store, "clone_session", side_effect=RuntimeError("DB down")):
            # Should not raise — compress should complete
            await agent._compress_context()
            # Compress succeeded (messages still in context)
            assert len(agent.context.messages) >= 2


class TestRestoreWithCheckpoint:
    """Tests for checkpoint-based context restore (fix-3)."""

    def test_restore_with_checkpoint_uses_summary(self, test_agent):
        """When compress_checkpoint exists, only summary + tail are loaded."""
        agent = test_agent
        agent.session.metadata["compress_checkpoint"] = {
            "summary": "[summary] user asked about X, agent did Y",
            "tail_count": 2, "original_count": 100, "compressed_at": 12345,
        }
        agent.session.add_message("user", "recent message 1")
        agent.session.add_message("assistant", "recent reply 1")
        agent.session.add_message("user", "recent message 2")
        agent._restore_context()
        # verify summary is in context, but not > 4 messages loaded
        assert len(agent.context.messages) <= 5  # summary + ~4 tail msgs
        assert "user asked about X" in agent.context.messages[0]["content"]

    def test_restore_without_checkpoint_loads_all(self, test_agent):
        """Without checkpoint, all session messages are loaded."""
        agent = test_agent
        agent.session.add_message("user", "msg1")
        agent.session.add_message("assistant", "msg2")
        agent._restore_context()
        assert len(agent.context.messages) >= 2

    def test_restore_with_checkpoint_no_summary(self, test_agent):
        """Checkpoint with empty summary: still loads tail only."""
        agent = test_agent
        agent.session.metadata["compress_checkpoint"] = {
            "summary": "",
            "tail_count": 1, "original_count": 50, "compressed_at": 99999,
        }
        agent.session.add_message("user", "msg1")
        agent.session.add_message("assistant", "msg2")
        agent.session.add_message("user", "msg3")
        agent.session.add_message("assistant", "msg4")
        agent._restore_context()
        # 1 tail turn = 2 msgs
        assert len(agent.context.messages) == 2

    def test_restore_with_checkpoint_preserves_tool_calls(self, test_agent):
        """Tail messages with tool_calls are loaded correctly."""
        agent = test_agent
        agent.session.metadata["compress_checkpoint"] = {
            "summary": "[summary] did some work",
            "tail_count": 1, "original_count": 20, "compressed_at": 555,
        }
        agent.session.add_message("assistant", "calling tool", tool_calls=[
            {"id": "tc1", "type": "function", "function": {"name": "echo", "arguments": "{}"}}
        ])
        agent._restore_context()
        msgs = agent.context.messages
        assert len(msgs) >= 1
        # The assistant message should have tool_calls
        assistant_msg = [m for m in msgs if m.get("role") == "assistant"]
        assert len(assistant_msg) >= 1
        assert "tool_calls" in assistant_msg[0]


def test_agent_has_mcp_manager(test_agent):
    assert hasattr(test_agent, 'mcp_manager')
    from merco.mcp.manager import MCPServerManager
    assert isinstance(test_agent.mcp_manager, MCPServerManager)


class TestRestorePreservesEmptyToolCallId:
    """修复根因 D：_restore_context 中 `msg.get("tool_call_id")` 的 truthy 过滤
    会丢弃空字符串 tool_call_id 字段。改用 `"tool_call_id" in msg` 保留字段。
    """

    def test_restore_context_preserves_empty_tool_call_id_main_branch(self, test_agent):
        """主分支：无 checkpoint 时，空 tool_call_id 必须保留在 context。"""
        agent = test_agent
        agent.session.add_message("tool", "取消", tool_call_id="")
        agent._restore_context()
        msgs = agent.context.messages
        assert len(msgs) == 1
        # 关键断言：tool_call_id 字段存在且为空字符串（不被 falsy 过滤）
        assert "tool_call_id" in msgs[-1]
        assert msgs[-1]["tool_call_id"] == ""
        assert msgs[-1]["role"] == "tool"
        assert msgs[-1]["content"] == "取消"

    def test_restore_context_preserves_empty_tool_call_id_checkpoint_branch(self, test_agent):
        """压缩分支：有 checkpoint 时，tail 中的空 tool_call_id 必须保留。"""
        agent = test_agent
        # 设 tail_count=2 → 拉最近 2*2=4 条消息
        agent.session.metadata["compress_checkpoint"] = {
            "summary": "[summary] user asked about X",
            "tail_count": 2,
            "original_count": 100,
            "compressed_at": 12345,
        }
        # 准备 4 条消息 + 1 条 tool 消息；最后一条 assistant 带 tool_calls
        agent.session.add_message("user", "msg1")
        agent.session.add_message("assistant", "msg2")
        agent.session.add_message("user", "msg3")
        agent.session.add_message(
            "assistant",
            "calling tool",
            tool_calls=[{"id": "tc1", "type": "function",
                         "function": {"name": "echo", "arguments": "{}"}}],
        )
        agent.session.add_message("tool", "tool result", tool_call_id="")

        agent._restore_context()
        msgs = agent.context.messages

        # 第一条应该是 summary system 消息
        assert msgs[0]["role"] == "system"
        assert "user asked about X" in msgs[0]["content"]

        # 找 tool 消息，断言 tool_call_id 字段保留为空字符串
        tool_msgs = [m for m in msgs if m.get("role") == "tool"]
        assert len(tool_msgs) == 1
        assert "tool_call_id" in tool_msgs[0]
        assert tool_msgs[0]["tool_call_id"] == ""


@pytest.mark.asyncio
async def test_agent_create_initializes_observer_via_plugin(monkeypatch, tmp_path):
    """Agent.create initializes observer through ObservabilityPlugin."""
    from merco.core.agent import Agent
    from merco.core.config import MercoConfig
    from merco.observability.observer import Observer
    from tests.conftest import MockLLMClient, make_test_registry

    db_path = str(tmp_path / "factory.db")
    monkeypatch.setattr("merco.core.agent.LLMClient", MockLLMClient)
    monkeypatch.setattr("merco.core.agent._get_db_path", lambda: db_path)

    cfg = MercoConfig()
    cfg.model.api_key = "test-key"
    cfg.model.model = "test-model"
    cfg.sandbox_mode = "auto"
    cfg.memory_path = str(tmp_path / "memory")

    agent = await Agent.create(config=cfg, tool_registry=make_test_registry())

    assert isinstance(agent.observer, Observer)
    assert "observability" in agent.plugin_manager.active_plugins


@pytest.mark.asyncio
async def test_agent_create_restores_observer_snapshot_after_plugin_activation(monkeypatch, tmp_path):
    """Factory path restores observer snapshot after ObservabilityPlugin creates observer."""
    from merco.core.agent import Agent
    from merco.core.config import MercoConfig
    from merco.memory.session_store import SessionStore
    from merco.core.session import Session
    from tests.conftest import MockLLMClient, make_test_registry

    db_path = str(tmp_path / "factory.db")
    store = SessionStore(db_path)
    existing = Session(store=store)
    existing.metadata["observer"] = {"acc": {"turns": 3}, "live": {}}
    existing.add_message("user", "hello")
    existing.save()
    store.save_metadata(existing.id, existing.metadata)

    monkeypatch.setattr("merco.core.agent.LLMClient", MockLLMClient)
    monkeypatch.setattr("merco.core.agent._get_db_path", lambda: db_path)

    cfg = MercoConfig()
    cfg.model.api_key = "test-key"
    cfg.model.model = "test-model"
    cfg.sandbox_mode = "auto"
    cfg.memory_path = str(tmp_path / "memory")

    agent = await Agent.create(config=cfg, tool_registry=make_test_registry())

    report = agent.observer.report()
    assert "3 轮" in report


@pytest.mark.asyncio
async def test_agent_create_still_activates_superpower_plugin(monkeypatch, tmp_path):
    """Factory path activates remaining enabled plugins after observability."""
    from merco.core.agent import Agent
    from merco.core.config import MercoConfig
    from tests.conftest import MockLLMClient, make_test_registry

    db_path = str(tmp_path / "factory.db")
    monkeypatch.setattr("merco.core.agent.LLMClient", MockLLMClient)
    monkeypatch.setattr("merco.core.agent._get_db_path", lambda: db_path)

    cfg = MercoConfig()
    cfg.model.api_key = "test-key"
    cfg.model.model = "test-model"
    cfg.sandbox_mode = "auto"
    cfg.memory_path = str(tmp_path / "memory")

    agent = await Agent.create(config=cfg, tool_registry=make_test_registry())

    assert "superpower" in agent.plugin_manager.active_plugins
    chunk_names = [chunk.name for chunk in agent.prompt_builder._chunks]
    assert "superpower_hint" in chunk_names


@pytest.mark.asyncio
async def test_agent_create_initializes_skill_registry(monkeypatch, tmp_path):
    """Agent.create loads SkillRegistry via SkillPlugin."""
    from merco.core.agent import Agent
    from merco.core.config import MercoConfig
    from merco.skills.registry import SkillRegistry
    from tests.conftest import MockLLMClient, make_test_registry

    db_path = str(tmp_path / "factory_skills.db")
    monkeypatch.setattr("merco.core.agent.LLMClient", MockLLMClient)
    monkeypatch.setattr("merco.core.agent._get_db_path", lambda: db_path)

    cfg = MercoConfig()
    cfg.model.api_key = "test-key"
    cfg.model.model = "test-model"
    cfg.sandbox_mode = "auto"
    cfg.memory_path = str(tmp_path / "memory")
    cfg.skills_paths = []

    agent = await Agent.create(config=cfg, tool_registry=make_test_registry())

    assert isinstance(agent.skill_registry, SkillRegistry)
    assert "skills" in agent.plugin_manager.active_plugins


@pytest.mark.asyncio
async def test_agent_create_injects_skill_registry_into_skill_view_tool(monkeypatch, tmp_path):
    """Agent.create makes SkillViewTool aware of the registry."""
    from merco.core.agent import Agent
    from merco.core.config import MercoConfig
    from merco.tools.skill_tools import SkillViewTool
    from tests.conftest import MockLLMClient, make_test_registry

    db_path = str(tmp_path / "factory_skill_view.db")
    monkeypatch.setattr("merco.core.agent.LLMClient", MockLLMClient)
    monkeypatch.setattr("merco.core.agent._get_db_path", lambda: db_path)

    cfg = MercoConfig()
    cfg.model.api_key = "test-key"
    cfg.model.model = "test-model"
    cfg.sandbox_mode = "auto"
    cfg.memory_path = str(tmp_path / "memory")
    cfg.skills_paths = []

    agent = await Agent.create(config=cfg, tool_registry=make_test_registry())
    skill_tool = agent.tool_registry.get("skill_view")

    assert skill_tool is not None
    assert isinstance(skill_tool, SkillViewTool)
    assert skill_tool._skill_registry is agent.skill_registry


def test_agent_init_no_longer_accepts_skill_registry(monkeypatch, tmp_path):
    """Agent.__init__ rejects skill_registry keyword argument."""
    from merco.core.agent import Agent
    from merco.core.config import MercoConfig
    from tests.conftest import MockLLMClient

    db_path = str(tmp_path / "factory_init_kw.db")
    monkeypatch.setattr("merco.core.agent.LLMClient", MockLLMClient)
    monkeypatch.setattr("merco.core.agent._get_db_path", lambda: db_path)

    cfg = MercoConfig()
    cfg.model.api_key = "test-key"
    cfg.model.model = "test-model"
    cfg.sandbox_mode = "auto"
    cfg.memory_path = str(tmp_path / "memory")

    with pytest.raises(TypeError):
        Agent(config=cfg, skill_registry=object())
