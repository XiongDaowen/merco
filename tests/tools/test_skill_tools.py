"""技能工具单元测试"""
from unittest.mock import MagicMock
import pytest
from merco.tools.skill_tools import SkillViewTool


class TestSkillViewTool:
    """SkillViewTool 测试"""

    @pytest.fixture
    def tool(self):
        """创建工具实例"""
        return SkillViewTool()

    @pytest.fixture
    def mock_registry(self):
        """模拟技能注册表"""
        registry = MagicMock()
        registry.list_skills.return_value = [
            {"name": "project-vision", "description": "项目愿景规划"},
            {"name": "debug-code", "description": "代码调试工具"}
        ]
        registry.get.return_value = {
            "name": "project-vision",
            "description": "项目愿景规划",
            "content": "# 项目愿景\n详细内容..."
        }
        return registry

    def test_describe_without_registry(self, tool):
        """测试没有注册表时的描述"""
        assert tool.describe() == "加载指定技能的完整说明文档。使用前先调用此工具获取详细指引。"

    def test_describe_with_registry(self, tool, mock_registry):
        """测试有注册表时的动态描述"""
        tool.set_skill_registry(mock_registry)
        description = tool.describe()

        assert "加载指定技能的完整说明文档" in description
        assert "可用技能：" in description
        assert "project-vision" in description
        assert "debug-code" in description
        assert "项目愿景规划" in description

    def test_describe_with_empty_registry(self, tool, mock_registry):
        """测试注册表为空时的描述"""
        mock_registry.list_skills.return_value = []
        tool.set_skill_registry(mock_registry)

        assert tool.describe() == "加载指定技能的完整说明文档。使用前先调用此工具获取详细指引。"

    def test_check_without_registry(self, tool):
        """测试没有注册表时工具不可用"""
        assert tool.check() is False

    def test_check_with_empty_registry(self, tool, mock_registry):
        """测试注册表为空时工具不可用"""
        mock_registry.list_skills.return_value = []
        tool.set_skill_registry(mock_registry)
        assert tool.check() is False

    def test_check_with_skills(self, tool, mock_registry):
        """测试有技能时工具可用"""
        tool.set_skill_registry(mock_registry)
        assert tool.check() is True

    @pytest.mark.asyncio
    async def test_execute_without_registry(self, tool):
        """测试没有注册表时执行返回错误"""
        result = await tool.execute("project-vision")
        assert result == {"error": "技能系统未初始化"}

    @pytest.mark.asyncio
    async def test_execute_skill_not_found(self, tool, mock_registry):
        """测试查找不存在的技能"""
        mock_registry.get.return_value = None
        tool.set_skill_registry(mock_registry)

        result = await tool.execute("nonexistent-skill")
        assert result["error"] == "未找到技能: nonexistent-skill"
        assert "available_skills" in result
        assert "project-vision" in result["available_skills"]
        assert "debug-code" in result["available_skills"]

    @pytest.mark.asyncio
    async def test_execute_skill_found(self, tool, mock_registry):
        """测试成功查找技能"""
        tool.set_skill_registry(mock_registry)

        result = await tool.execute("project-vision")
        assert result["name"] == "project-vision"
        assert result["description"] == "项目愿景规划"
        assert result["content"] == "# 项目愿景\n详细内容..."
        mock_registry.get.assert_called_once_with("project-vision")
