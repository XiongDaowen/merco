"""集成测试顶层conftest"""

from pathlib import Path

import pytest

from merco.sandbox import snapshot
from merco.sandbox.guard import ToolGuard
from merco.scheduler.cron import CronScheduler
from merco.skills.registry import SkillRegistry
from tests.integration.core.programmable_mock import ProgrammableModelProvider
from tests.integration.core.scenario import TestScenario, build_scenario_agent


@pytest.fixture
def isolation_services(tmp_path, monkeypatch):
    """为每个场景创建独立的有状态服务"""
    # 1. 快照 -> tmp_path/snapshots/
    snapshot_root = tmp_path / "snapshots"
    monkeypatch.setattr(snapshot, "SNAPSHOT_DIR", snapshot_root)

    # 2. Todo -> tmp_path/todos.db
    todo_db = tmp_path / "todos.db"

    # 3. 调度器 -> 独立实例
    scheduler = CronScheduler()

    # 4. Guard -> 独立实例
    guard = ToolGuard()

    # 5. SkillRegistry -> 独立实例
    skill_registry = SkillRegistry()

    return {
        "snapshot_root": snapshot_root,
        "todo_db": todo_db,
        "scheduler": scheduler,
        "guard": guard,
        "skill_registry": skill_registry,
    }


@pytest.fixture
def programmable_provider() -> ProgrammableModelProvider:
    """可编程LLM mock"""
    return ProgrammableModelProvider()


@pytest.fixture
async def scenario(
    tmp_path: Path,
    isolation_services: dict,
    programmable_provider: ProgrammableModelProvider,
    monkeypatch,
) -> TestScenario:
    """集成测试场景入口"""
    agent = await build_scenario_agent(provider=programmable_provider, tmp_path=tmp_path, monkeypatch=monkeypatch)

    # 将隔离的Guard实例通过GuardMiddleware包装后注入中间件链
    from merco.tools.middleware import GuardMiddleware

    guard_mw = GuardMiddleware(isolation_services["guard"])
    agent.tool_registry.use(guard_mw)

    # Agent 默认会拦截 GuardConfirmationRequired 并弹出 stdin 确认；
    # 测试场景里我们让它直接重新抛出，便于断言。
    from merco.sandbox.guard import GuardConfirmationRequired

    async def _raise_guard_confirmation(result):
        raise GuardConfirmationRequired(result)

    monkeypatch.setattr(agent, "_ask_guard_confirmation", _raise_guard_confirmation)

    # 将隔离的SkillRegistry注入到Agent
    agent.skill_registry = isolation_services["skill_registry"]
    # 同步更新 SkillViewTool 的 _skill_registry，确保 check()/describe()/execute() 使用隔离实例
    skill_tool = agent.tool_registry.get("skill_view")
    if skill_tool is not None and hasattr(skill_tool, "set_skill_registry"):
        skill_tool.set_skill_registry(agent.skill_registry)

    return TestScenario(
        agent=agent,
        provider=programmable_provider,
        tmp_path=tmp_path,
        **isolation_services,
    )
