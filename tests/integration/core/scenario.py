"""TestScenario上下文对象与Agent构建器"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from merco.core.agent import Agent
from merco.sandbox.guard import (
    GuardAction,
    GuardResult,
    PermissionPolicy,
)
from tests.integration.core.programmable_mock import ProgrammableModelProvider


class _FixedActionPolicy(PermissionPolicy):
    """测试用策略：对指定工具返回固定动作与原因"""

    name = "test_fixed_action"

    def __init__(self, tool_name: str, action: GuardAction, reason: str = ""):
        self._tool_name = tool_name
        self._action = action
        self._reason = reason

    async def check(self, tool_name, arguments):
        if tool_name != self._tool_name:
            return None
        command = arguments.get("command", arguments.get("path", ""))
        return GuardResult(
            action=self._action,
            command=command,
            reason=self._reason,
        )


@dataclass
class TestScenario:
    """集成测试场景上下文对象"""

    agent: Agent
    provider: ProgrammableModelProvider
    snapshot_root: Path
    todo_db: Path
    scheduler: object
    guard: object
    skill_registry: object
    tmp_path: Path

    async def run(self, user_input: str) -> str:
        return await self.agent.run(user_input)

    @property
    def messages(self) -> list[dict]:
        return list(self.agent.context.messages)

    @property
    def session(self):
        return self.agent.session

    @property
    def tool_calls(self) -> list[dict]:
        calls = []
        for msg in self.messages:
            if msg.get("role") == "assistant":
                for tc in msg.get("tool_calls", []) or []:
                    calls.append(tc)
        return calls

    def set_guard_action(self, tool_name: str, action: GuardAction, reason: str = "") -> None:
        """为测试注入 guard 行为 — 在 pipeline 顶部插入固定动作策略"""
        self.guard._pipeline._policies.insert(
            0,
            _FixedActionPolicy(tool_name, action, reason),
        )


async def build_scenario_agent(provider: ProgrammableModelProvider, tmp_path: Path, monkeypatch) -> Agent:
    """构建一个集成测试专用Agent"""
    # 参考根conftest.py的test_agent fixture构造
    from merco.core.agent import Agent
    from merco.core.config import MercoConfig

    # 临时数据库路径
    db_path = str(tmp_path / "agent.db")

    # Patch _get_db_path让它返回我们的临时路径，避免读取全局历史
    monkeypatch.setattr("merco.core.agent._get_db_path", lambda: db_path)

    # 构造config
    cfg = MercoConfig()
    cfg.model.api_key = "test-key"
    cfg.model.model = "test-model"
    cfg.sandbox_mode = "auto"
    cfg.memory_path = str(tmp_path / "memory")  # 隔离memory目录

    # 使用根conftest里的make_test_registry()
    from tests.conftest import make_test_registry

    reg = make_test_registry()

    # 用Agent.create()异步工厂
    agent = await Agent.create(config=cfg, tool_registry=reg)
    agent.provider = provider  # 替换为我们的ProgrammableModelProvider
    return agent
