"""SubAgentManager profile 单测"""

import pytest

from merco.agents.profile import AgentProfile


class TestSubAgentProfile:
    @pytest.mark.asyncio
    async def test_create_with_researcher_profile(self, test_agent):
        """researcher profile 工具过滤"""
        from merco.agents.profile import BUILTIN_PROFILES, AgentProfileRegistry
        from merco.agents.subagent import SubAgentManager

        reg = AgentProfileRegistry()
        for p in BUILTIN_PROFILES:
            reg.register(p)

        manager = SubAgentManager(test_agent, reg)
        sub_agent = await manager._create_sub_agent("researcher")

        # researcher 有限制工具列表
        tool_names = [t.name for t in sub_agent.tool_registry.list_tools()]
        for name in tool_names:
            assert name in ["read_file", "web_fetch", "web_search"]

    @pytest.mark.asyncio
    async def test_default_when_profile_not_found(self, test_agent):
        """不存在的 profile 回退到 default"""
        from merco.agents.profile import BUILTIN_PROFILES, AgentProfileRegistry
        from merco.agents.subagent import SubAgentManager

        reg = AgentProfileRegistry()
        for p in BUILTIN_PROFILES:
            reg.register(p)

        manager = SubAgentManager(test_agent, reg)
        sub_agent = await manager._create_sub_agent("nonexistent")
        # default 不限制工具，应继承全部
        assert sub_agent.tool_registry == test_agent.tool_registry

    @pytest.mark.asyncio
    async def test_profile_prompt_injected(self, test_agent):
        """profile prompt chunk 被注入"""
        from merco.agents.profile import BUILTIN_PROFILES, AgentProfileRegistry
        from merco.agents.subagent import SubAgentManager

        reg = AgentProfileRegistry()
        for p in BUILTIN_PROFILES:
            reg.register(p)

        manager = SubAgentManager(test_agent, reg)
        sub_agent = await manager._create_sub_agent("debugger")
        chunks = sub_agent.prompt_builder._chunks
        assert any(c.name == "agent_profile" for c in chunks)

    @pytest.mark.asyncio
    async def test_model_override_from_profile(self, test_agent):
        """profile 指定 model 时覆盖子代理的 config"""
        from merco.agents.profile import AgentProfileRegistry
        from merco.agents.subagent import SubAgentManager

        reg = AgentProfileRegistry()
        reg.register(
            AgentProfile(
                name="gpt4",
                description="GPT-4 sub",
                prompt="you are gpt4",
                model={"provider": "openai", "model": "gpt-4o"},
            )
        )

        manager = SubAgentManager(test_agent, reg)
        sub_agent = await manager._create_sub_agent("gpt4")
        assert sub_agent.config.model.provider == "openai"
        assert sub_agent.config.model.model == "gpt-4o"
        # parent config should not be mutated
        assert test_agent.config.model.model == "test-model"

    @pytest.mark.asyncio
    async def test_limits_applied(self, test_agent):
        """profile.limits.max_tool_calls 覆盖子代理限制"""
        from merco.agents.profile import AgentProfileRegistry
        from merco.agents.subagent import SubAgentManager

        reg = AgentProfileRegistry()
        reg.register(
            AgentProfile(
                name="limited",
                description="limited agent",
                prompt="you are limited",
                limits={"max_tool_calls": 10},
            )
        )

        manager = SubAgentManager(test_agent, reg)
        sub_agent = await manager._create_sub_agent("limited")
        assert sub_agent._max_tool_calls == 10

    @pytest.mark.asyncio
    async def test_backward_compat_no_registry(self, test_agent):
        """profile_registry=None 时正常创建子代理（向后兼容）"""
        from merco.agents.subagent import SubAgentManager

        manager = SubAgentManager(test_agent)
        sub_agent = await manager._create_sub_agent("default")
        # 应继承父的全部配置
        assert sub_agent.config == test_agent.config
        assert sub_agent.tool_registry == test_agent.tool_registry
        assert sub_agent.session.id != test_agent.session.id
