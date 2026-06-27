"""Agent LoopPolicy — 可拔插循环策略"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class LoopState:
    """Loop 当前状态"""
    iteration: int
    tool_calls_count: int
    max_tool_calls: int
    has_tool_calls: bool
    finish_reason: str | None = None


@dataclass
class LoopDecision:
    """Loop 策略决策"""
    action: str  # "continue" | "exit"
    reason: str = ""


class LoopPolicy(ABC):
    """Agent Loop 策略基类"""
    name: str = ""

    @abstractmethod
    async def decide(self, response: dict, state: LoopState) -> LoopDecision:
        """根据 LLM response 和当前 state 决定继续或退出"""
        ...


class DefaultLoopPolicy(LoopPolicy):
    """默认策略：完全复刻当前行为"""
    name = "default"

    async def decide(self, response: dict, state: LoopState) -> LoopDecision:
        if state.has_tool_calls:
            return LoopDecision(action="continue", reason="tool_calls present")
        return LoopDecision(action="exit", reason="no tool_calls")


class LoopPolicyRegistry:
    """LoopPolicy 注册表"""

    def __init__(self):
        self._policies: dict[str, LoopPolicy] = {}
        self._active: str = "default"

    def register(self, policy: LoopPolicy) -> None:
        self._policies[policy.name] = policy

    def get(self, name: str) -> LoopPolicy | None:
        return self._policies.get(name)

    def list(self) -> list[LoopPolicy]:
        return list(self._policies.values())

    def set_active(self, name: str) -> None:
        if name not in self._policies:
            raise KeyError(name)
        self._active = name

    @property
    def active(self) -> LoopPolicy:
        return self._policies[self._active]
