"""技能注册表单元测试"""
import tempfile
import os
from unittest.mock import patch, MagicMock
import pytest
from merco.skills.registry import SkillRegistry


class TestSkillRegistry:
    """SkillRegistry 测试"""

    @pytest.fixture
    def registry(self):
        """创建空的技能注册表"""
        return SkillRegistry()

    @pytest.fixture
    def sample_skills(self):
        """示例技能数据"""
        return [
            {
                "name": "project-vision",
                "description": "项目愿景规划与文档生成",
                "content": "# 项目愿景\n..."
            },
            {
                "name": "debug-code",
                "description": "代码调试与错误修复",
                "content": "# 调试指南\n..."
            },
            {
                "name": "code-review",
                "description": "代码审查与质量评估",
                "content": "# 审查标准\n..."
            }
        ]

    def test_register_and_get_skill(self, registry, sample_skills):
        """测试注册和获取技能"""
        skill = sample_skills[0]
        registry.register(skill)

        # 获取存在的技能
        retrieved = registry.get(skill["name"])
        assert retrieved == skill

        # 获取不存在的技能
        assert registry.get("nonexistent") is None

    def test_unregister_skill(self, registry, sample_skills):
        """测试注销技能"""
        skill = sample_skills[0]
        registry.register(skill)

        # 注销存在的技能
        registry.unregister(skill["name"])
        assert registry.get(skill["name"]) is None

        # 注销不存在的技能不报错
        registry.unregister("nonexistent")

    def test_list_skills(self, registry, sample_skills):
        """测试列出所有技能"""
        # 空列表
        assert registry.list_skills() == []

        # 注册多个技能
        for skill in sample_skills:
            registry.register(skill)

        skills = registry.list_skills()
        assert len(skills) == 3
        skill_names = [s["name"] for s in skills]
        assert "project-vision" in skill_names
        assert "debug-code" in skill_names
        assert "code-review" in skill_names

    def test_get_relevant_skills(self, registry, sample_skills):
        """测试获取相关技能（关键词匹配）"""
        for skill in sample_skills:
            registry.register(skill)

        # 匹配名称
        relevant = registry.get_relevant("project")
        assert len(relevant) == 1
        assert relevant[0]["name"] == "project-vision"

        # 匹配描述
        relevant = registry.get_relevant("debug")
        assert len(relevant) == 1
        assert relevant[0]["name"] == "debug-code"

        # 匹配多个
        relevant = registry.get_relevant("code")
        assert len(relevant) == 2  # debug-code和code-review都匹配
        skill_names = [s["name"] for s in relevant]
        assert "debug-code" in skill_names
        assert "code-review" in skill_names

        # 不匹配
        relevant = registry.get_relevant("nonexistent")
        assert len(relevant) == 0

        # 大小写不敏感
        relevant = registry.get_relevant("PROJECT")
        assert len(relevant) == 1
        assert relevant[0]["name"] == "project-vision"

    def test_get_relevant_skills_with_missing_fields(self, registry):
        """测试技能缺少名称时拒绝注册"""
        # 技能没有描述 — 可以正常注册
        skill1 = {"name": "test-skill"}
        registry.register(skill1)

        # 技能没有名称 — 应该抛出 KeyError（拒绝注册残缺技能）
        skill2 = {"description": "测试技能"}
        with pytest.raises(KeyError):
            registry.register(skill2)

        # skill1 正常匹配
        relevant = registry.get_relevant("test")
        assert len(relevant) == 1
        assert relevant[0]["name"] == "test-skill"

    @pytest.mark.asyncio
    async def test_load_from_paths(self, registry, sample_skills):
        """测试从路径加载技能"""
        # 创建临时目录
        with tempfile.TemporaryDirectory() as tmpdir:
            # 创建技能文件
            skill_dir = os.path.join(tmpdir, "skills")
            os.makedirs(skill_dir)

            # 模拟SkillLoader（classmethod，直接在类上设置）
            with patch("merco.skills.loader.SkillLoader") as mock_loader_class:
                mock_loader_class.load_from_directory.return_value = sample_skills

                # 加载技能
                registry.load_from_paths([skill_dir])

                # 验证加载
                assert len(registry.list_skills()) == 3
                mock_loader_class.load_from_directory.assert_called_once_with(skill_dir)

    def test_load_from_paths_multiple_dirs(self, registry):
        """测试从多个目录加载技能"""
        with tempfile.TemporaryDirectory() as tmpdir1, tempfile.TemporaryDirectory() as tmpdir2:
            with patch("merco.skills.loader.SkillLoader") as mock_loader_class:
                mock_loader_class.load_from_directory.side_effect = [
                    [{"name": "skill1"}],
                    [{"name": "skill2"}, {"name": "skill3"}]
                ]

                registry.load_from_paths([tmpdir1, tmpdir2])

                assert len(registry.list_skills()) == 3
                assert mock_loader_class.load_from_directory.call_count == 2
