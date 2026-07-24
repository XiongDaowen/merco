"""技能处理器单元测试"""
import pytest

from merco.core.pipeline import ProcessContext
from merco.skills.processors import SkillViewProcessor


class TestSkillViewProcessor:
    """SkillViewProcessor 测试"""

    @pytest.fixture
    def processor(self):
        """创建处理器实例"""
        return SkillViewProcessor()

    @pytest.fixture
    def process_ctx(self):
        """创建处理上下文"""
        ctx = ProcessContext(
            tool_name="skill_view",
            arguments={"name": "project-vision"},
            result={
                "name": "project-vision",
                "description": "项目愿景规划",
                "content": "# 项目愿景\n这是技能内容..."
            },
            extra_messages=[]
        )
        return ctx

    @pytest.mark.asyncio
    async def test_process_other_tool(self, processor, process_ctx):
        """测试处理其他工具时跳过"""
        process_ctx.tool_name = "other-tool"

        result = await processor.process(process_ctx)
        assert result is False
        # 结果没有被修改
        assert process_ctx.result["content"] == "# 项目愿景\n这是技能内容..."
        # 没有添加额外消息
        assert len(process_ctx.extra_messages) == 0

    @pytest.mark.asyncio
    async def test_process_result_with_error(self, processor, process_ctx):
        """测试结果包含错误时跳过"""
        process_ctx.result["error"] = "技能未找到"

        result = await processor.process(process_ctx)
        assert result is False
        # 结果没有被修改
        assert "error" in process_ctx.result
        # 没有添加额外消息
        assert len(process_ctx.extra_messages) == 0

    @pytest.mark.asyncio
    async def test_process_result_without_content(self, processor, process_ctx):
        """测试结果不包含content字段时跳过"""
        del process_ctx.result["content"]

        result = await processor.process(process_ctx)
        assert result is False
        # 没有添加额外消息
        assert len(process_ctx.extra_messages) == 0

    @pytest.mark.asyncio
    async def test_process_success_short_content(self, processor, process_ctx):
        """测试成功处理短内容（不需要截断）"""
        result = await processor.process(process_ctx)

        assert result is False  # 不停止管线
        # 原结果被替换为占位信息
        assert "技能 project-vision 已加载" in process_ctx.result["content"]
        assert "字符" in process_ctx.result["content"]
        # 添加了额外的用户消息
        assert len(process_ctx.extra_messages) == 1
        extra_msg = process_ctx.extra_messages[0]
        assert extra_msg["role"] == "user"
        assert "技能 **project-vision** 已加载" in extra_msg["content"]
        assert "# 项目愿景\n这是技能内容..." in extra_msg["content"]

    @pytest.mark.asyncio
    async def test_process_success_long_content_truncated(self, processor, process_ctx):
        """测试成功处理长内容（自动截断）"""
        # 创建很长的内容
        long_content = "# 长技能内容\n" + "x" * 9000
        process_ctx.result["content"] = long_content

        result = await processor.process(process_ctx)

        assert result is False
        # 额外消息被截断
        extra_msg = process_ctx.extra_messages[0]
        assert len(extra_msg["content"]) <= 8000
        assert "技能内容过长，已截断" in extra_msg["content"]

    @pytest.mark.asyncio
    async def test_process_without_skill_name(self, processor, process_ctx):
        """测试技能结果没有name字段时使用默认值"""
        del process_ctx.result["name"]

        result = await processor.process(process_ctx)

        assert result is False
        assert "技能 unknown 已加载" in process_ctx.result["content"]
        assert "技能 **unknown** 已加载" in process_ctx.extra_messages[0]["content"]
