"""AgentProfile data model and registry"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AgentProfile:
    """Professional role configuration for sub-agents"""
    name: str
    description: str
    prompt: str
    tools: list[str] = field(default_factory=list)
    model: dict | None = None
    limits: dict = field(default_factory=dict)


class AgentProfileRegistry:
    """Registry for AgentProfile instances"""

    def __init__(self):
        self._profiles: dict[str, AgentProfile] = {}

    def register(self, profile: AgentProfile) -> None:
        self._profiles[profile.name] = profile

    def get(self, name: str) -> AgentProfile | None:
        return self._profiles.get(name)

    def list(self) -> list[AgentProfile]:
        return list(self._profiles.values())


class ProfilePromptChunk:
    """Prompt chunk that injects agent role from profile"""
    name = "agent_profile"

    def __init__(self, profile: AgentProfile):
        self.profile = profile

    def enabled(self, agent) -> bool:
        return True

    def build(self, agent) -> str:
        return f"## Agent Role: {self.profile.name}\n{self.profile.prompt}"


BUILTIN_PROFILES: list[AgentProfile] = [
    AgentProfile(
        name="default",
        description="普通子代理，继承父代理全部能力",
        prompt="你是 merco 子代理。完成父代理委派的任务，返回简洁明确的结果。",
    ),
    AgentProfile(
        name="researcher",
        description="代码搜索、资料收集、架构理解",
        prompt="你是代码研究员。专注于阅读代码、搜索资料、归纳结构，不做大规模修改。输出清晰的发现和证据。",
        tools=["read_file", "web_fetch", "web_search"],
        limits={"max_tool_calls": 30},
    ),
    AgentProfile(
        name="reviewer",
        description="代码审查、bug 风险识别、质量检查",
        prompt="你是代码审查专家。专注于发现 correctness bug、边界条件、测试缺口和架构问题。只报告高置信问题。",
        tools=["read_file", "grep", "bash"],
        limits={"max_tool_calls": 25},
    ),
    AgentProfile(
        name="debugger",
        description="系统调试、根因分析、失败复现",
        prompt="你是系统调试专家。先定位症状，再建立假设，最后用测试/日志验证。不要盲改。",
        tools=["read_file", "bash", "grep"],
        limits={"max_tool_calls": 40},
    ),
]
