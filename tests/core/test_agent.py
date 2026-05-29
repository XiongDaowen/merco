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
