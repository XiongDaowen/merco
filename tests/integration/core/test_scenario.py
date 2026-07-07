"""TestScenario上下文对象测试"""
import pytest

class TestBuildScenarioAgent:
    @pytest.mark.asyncio
    async def test_returns_agent_with_programmable_llm(self, programmable_llm, tmp_path, monkeypatch):
        from tests.integration.core.scenario import build_scenario_agent
        agent = await build_scenario_agent(llm=programmable_llm, tmp_path=tmp_path, monkeypatch=monkeypatch)
        assert agent.llm is programmable_llm
        assert agent.tool_registry is not None
        assert agent.plugin_manager is not None

class TestTestScenario:
    @pytest.mark.asyncio
    async def test_scenario_attributes(self, scenario):
        assert scenario.agent is not None
        assert scenario.llm is not None
        assert scenario.snapshot_root is not None
        assert scenario.todo_db is not None
        assert scenario.scheduler is not None
        assert scenario.guard is not None
        assert scenario.skill_registry is not None
        assert scenario.tmp_path is not None

    @pytest.mark.asyncio
    async def test_scenario_messages_property_returns_list(self, scenario):
        assert isinstance(scenario.messages, list)
        assert len(scenario.messages) == 0

    @pytest.mark.asyncio
    async def test_scenario_session_property(self, scenario):
        assert scenario.session is not None
        assert scenario.session == scenario.agent.session

    @pytest.mark.asyncio
    async def test_scenario_tool_calls_property_empty_initially(self, scenario):
        assert scenario.tool_calls == []

    @pytest.mark.asyncio
    async def test_scenario_run_method_executes_agent(self, scenario):
        from tests.integration.core.programmable_mock import Response
        scenario.llm.expect([Response.content("hello")])
        result = await scenario.run("hi")
        assert result == "hello"
        assert len(scenario.messages) == 2