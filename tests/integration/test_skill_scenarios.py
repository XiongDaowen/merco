"""技能系统集成测试 — 覆盖技能发现、加载、注入上下文完整流程。"""
import pytest
from tests.integration.core.programmable_mock import Response


class TestSkillDescribe:
    def test_skill_view_describe_lists_skills(self, scenario):
        scenario.skill_registry.register({
            "name": "project-vision",
            "description": "项目愿景规划与文档生成",
            "content": "# 项目愿景\n...",
        })
        scenario.skill_registry.register({
            "name": "debug-code",
            "description": "代码调试与错误修复",
            "content": "# 调试指南\n...",
        })

        definitions = scenario.agent.tool_registry.get_definitions()
        skill_view_def = next(
            d for d in definitions if d["function"]["name"] == "skill_view"
        )
        desc = skill_view_def["function"]["description"]
        assert "project-vision" in desc
        assert "debug-code" in desc
        assert "项目愿景规划" in desc

    def test_skill_view_disabled_when_no_skills(self, scenario):
        definitions = scenario.agent.tool_registry.get_definitions()
        tool_names = {d["function"]["name"] for d in definitions}
        assert "skill_view" not in tool_names


class TestSkillViewExecution:
    @pytest.mark.asyncio
    async def test_skill_view_loads_content_into_context(self, scenario):
        scenario.skill_registry.register({
            "name": "test-skill",
            "description": "测试技能",
            "content": "# 技能内容\n遵循以下步骤...",
        })

        scenario.provider.expect([
            Response.tool_call("skill_view", {"name": "test-skill"}),
            Response.content("已加载技能"),
        ])

        await scenario.run("加载测试技能")

        user_msgs = [m for m in scenario.messages if m["role"] == "user"]
        skill_injected = any(
            "test-skill" in m["content"] and "技能内容" in m["content"]
            for m in user_msgs
        )
        assert skill_injected

    @pytest.mark.asyncio
    async def test_skill_view_long_content_truncated(self, scenario):
        long_content = "# 长技能\n" + ("x" * 9000)
        scenario.skill_registry.register({
            "name": "long-skill",
            "description": "长技能",
            "content": long_content,
        })

        scenario.provider.expect([
            Response.tool_call("skill_view", {"name": "long-skill"}),
            Response.content("已加载"),
        ])

        await scenario.run("加载长技能")

        user_msgs = [m for m in scenario.messages if m["role"] == "user"]
        skill_msg = next(m for m in user_msgs if "long-skill" in m["content"])
        assert len(skill_msg["content"]) <= 8000
        assert "技能内容过长" in skill_msg["content"]

    @pytest.mark.asyncio
    async def test_skill_view_not_found(self, scenario):
        scenario.skill_registry.register({
            "name": "existing-skill",
            "description": "已存在",
            "content": "...",
        })

        scenario.provider.expect([
            Response.tool_call("skill_view", {"name": "nonexistent"}),
            Response.content("换个技能试试"),
        ])

        await scenario.run("加载不存在的技能")

        tool_msg = next(m for m in scenario.messages if m["role"] == "tool")
        assert "未找到技能: nonexistent" in tool_msg["content"]
        assert "existing-skill" in tool_msg["content"]


class TestSkillDiscovery:
    def test_relevant_skills_by_keyword(self, scenario):
        scenario.skill_registry.register({
            "name": "code-review",
            "description": "代码审查与质量评估",
            "content": "...",
        })
        scenario.skill_registry.register({
            "name": "project-vision",
            "description": "项目愿景规划",
            "content": "...",
        })

        relevant = scenario.skill_registry.get_relevant("代码")
        names = [s["name"] for s in relevant]
        assert "code-review" in names

        relevant = scenario.skill_registry.get_relevant("项目")
        names = [s["name"] for s in relevant]
        assert "project-vision" in names

    @pytest.mark.asyncio
    async def test_skill_view_appears_in_tool_definitions(self, scenario):
        scenario.skill_registry.register({
            "name": "test-skill",
            "description": "测试",
            "content": "...",
        })

        definitions = scenario.agent.tool_registry.get_definitions()
        tool_names = {d["function"]["name"] for d in definitions}
        assert "skill_view" in tool_names
