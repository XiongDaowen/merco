"""集成测试顶层conftest"""
import pytest
from pathlib import Path

from tests.integration.core.programmable_mock import ProgrammableModelProvider
from tests.integration.core.scenario import TestScenario, build_scenario_agent
from tests.integration.core.isolation import isolation_services as _isolation_services


@pytest.fixture
def programmable_provider() -> ProgrammableModelProvider:
    """可编程LLM mock"""
    return ProgrammableModelProvider()


@pytest.fixture
async def scenario(
    tmp_path: Path,
    _isolation_services: dict,
    programmable_provider: ProgrammableModelProvider,
    monkeypatch,
) -> TestScenario:
    """集成测试场景入口"""
    agent = await build_scenario_agent(provider=programmable_provider, tmp_path=tmp_path, monkeypatch=monkeypatch)

    # 将隔离的Guard实例通过GuardMiddleware包装后注入中间件链
    from merco.tools.middleware import GuardMiddleware
    guard_mw = GuardMiddleware(_isolation_services["guard"])
    agent.tool_registry.use(guard_mw)

    # Agent 默认会拦截 GuardConfirmationRequired 并弹出 stdin 确认；
    # 测试场景里我们让它直接重新抛出，便于断言。
    from merco.sandbox.guard import GuardConfirmationRequired

    async def _raise_guard_confirmation(result):
        raise GuardConfirmationRequired(result)

    monkeypatch.setattr(agent, "_ask_guard_confirmation", _raise_guard_confirmation)

    # 将隔离的SkillRegistry注入到Agent
    agent.skill_registry = _isolation_services["skill_registry"]
    # 同步更新 SkillViewTool 的 _skill_registry，确保 check()/describe()/execute() 使用隔离实例
    skill_tool = agent.tool_registry.get("skill_view")
    if skill_tool is not None and hasattr(skill_tool, "set_skill_registry"):
        skill_tool.set_skill_registry(agent.skill_registry)

    return TestScenario(
        agent=agent,
        provider=programmable_provider,
        tmp_path=tmp_path,
        **_isolation_services,
    )


# 重新导出给测试用
@pytest.fixture
def isolation_services(_isolation_services):
    """重命名以避免与内部fixture冲突"""
    return _isolation_services