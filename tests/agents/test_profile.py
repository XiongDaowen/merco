"""AgentProfile + Registry 单测"""

from merco.agents.profile import BUILTIN_PROFILES, AgentProfile, AgentProfileRegistry


class TestAgentProfile:
    def test_agent_profile_creation(self):
        p = AgentProfile(name="qa", description="qa agent", prompt="you test things")
        assert p.name == "qa"
        assert p.tools == []
        assert p.model is None
        assert p.limits == {}

    def test_agent_profile_with_all_fields(self):
        p = AgentProfile(
            name="expert",
            description="deep agent",
            prompt="you are expert",
            tools=["read_file", "grep"],
            model={"provider": "openai", "model": "gpt-4o"},
            limits={"max_tool_calls": 20},
        )
        assert p.tools == ["read_file", "grep"]
        assert p.model["model"] == "gpt-4o"
        assert p.limits["max_tool_calls"] == 20


class TestAgentProfileRegistry:
    def test_register_and_get(self):
        reg = AgentProfileRegistry()
        reg.register(AgentProfile(name="test", description="test", prompt="test prompt"))
        assert reg.get("test").name == "test"
        assert reg.get("nonexistent") is None

    def test_list_profiles(self):
        reg = AgentProfileRegistry()
        reg.register(AgentProfile(name="a", description="a", prompt="a"))
        reg.register(AgentProfile(name="b", description="b", prompt="b"))
        assert len(reg.list()) == 2


class TestBuiltinProfiles:
    def test_has_four_builtins(self):
        assert len(BUILTIN_PROFILES) == 4
        names = {p.name for p in BUILTIN_PROFILES}
        assert names == {"default", "researcher", "reviewer", "debugger"}

    def test_researcher_has_tools_allowlist(self):
        researcher = next(p for p in BUILTIN_PROFILES if p.name == "researcher")
        assert len(researcher.tools) > 0
        assert researcher.limits.get("max_tool_calls") == 30
