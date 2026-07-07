"""集成测试顶层conftest"""
import pytest
from pathlib import Path

from tests.integration.core.programmable_mock import ProgrammableLLMClient
from tests.integration.core.scenario import TestScenario, build_scenario_agent
from tests.integration.core.isolation import isolation_services as _isolation_services


@pytest.fixture
def programmable_llm() -> ProgrammableLLMClient:
    """可编程LLM mock"""
    return ProgrammableLLMClient()


@pytest.fixture
async def scenario(
    tmp_path: Path,
    _isolation_services: dict,
    programmable_llm: ProgrammableLLMClient,
    monkeypatch,
) -> TestScenario:
    """集成测试场景入口"""
    agent = await build_scenario_agent(llm=programmable_llm, tmp_path=tmp_path, monkeypatch=monkeypatch)

    # 将隔离的Guard实例注入到Agent的ToolRegistry的中间件
    # 确保测试中的Guard配置生效
    agent.tool_registry.use(_isolation_services["guard"])

    # 将隔离的SkillRegistry注入到Agent
    agent.skill_registry = _isolation_services["skill_registry"]

    return TestScenario(
        agent=agent,
        llm=programmable_llm,
        tmp_path=tmp_path,
        **_isolation_services,
    )


# 重新导出给测试用
@pytest.fixture
def isolation_services(_isolation_services):
    """重命名以避免与内部fixture冲突"""
    return _isolation_services