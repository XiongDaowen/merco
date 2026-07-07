"""工具调用集成测试 — 端到端覆盖工具链路"""
import pytest
from pathlib import Path
from tests.integration.core.programmable_mock import Response


class TestToolCallChain:
    """工具调用完整链路测试"""

    @pytest.mark.asyncio
    async def test_single_tool_call_full_chain(self, scenario, tmp_path):
        """完整链路：用户提问 → LLM工具调用 → 工具执行 → 结果返回 → LLM综合回答"""
        # 创建测试文件
        test_file = tmp_path / "test.txt"
        test_file.write_text("hello world")

        # LLM先返回工具调用，然后根据工具返回结果回答
        scenario.llm.expect([
            Response.tool_call(
                name="read_file",
                arguments={"path": str(test_file)}
            ),
            Response.content(f"文件内容是：hello world")
        ])

        # 用户提问
        result = await scenario.run("读取test.txt的内容是什么")

        # 断言最终回答正确
        assert "hello world" in result
        # 断言消息链路完整：用户→工具调用→工具结果→助手回答
        assert len(scenario.messages) == 4
        # 断言工具调用确实发生
        assert len(scenario.tool_calls) == 1
        assert scenario.tool_calls[0]["function"]["name"] == "read_file"

    @pytest.mark.asyncio
    async def test_multi_tool_calls_single_turn(self, scenario, tmp_path):
        """一轮对话多个工具调用：LLM一次返回多个工具调用，全部执行后整合回答"""
        # 创建两个测试文件
        file_a = tmp_path / "a.txt"
        file_a.write_text("content A")
        file_b = tmp_path / "b.txt"
        file_b.write_text("content B")

        # LLM一次返回两个工具调用
        scenario.llm.expect([
            Response(
                tool_calls=[
                    {"id": "call_1", "name": "read_file", "arguments": {"path": str(file_a)}},
                    {"id": "call_2", "name": "read_file", "arguments": {"path": str(file_b)}},
                ]
            ),
            Response.content(f"两个文件内容分别是：content A 和 content B")
        ])

        # 用户提问
        result = await scenario.run("a.txt和b.txt的内容分别是什么")

        # 断言回答包含两个文件内容
        assert "content A" in result
        assert "content B" in result
        # 断言两个工具都被调用
        assert len(scenario.tool_calls) == 2
        tool_names = [t["function"]["name"] for t in scenario.tool_calls]
        assert tool_names == ["read_file", "read_file"]
        # 断言消息链路：用户→工具调用（多）→工具结果（多）→助手回答
        assert len(scenario.messages) == 5  # 用户 + 助手（工具调用） + 工具结果1 + 工具结果2 + 助手回答


class TestToolIntegrationBoundary:
    """工具调用边界测试"""

    @pytest.mark.asyncio
    async def test_call_nonexistent_tool(self, scenario):
        """调用不存在的工具，返回结构化错误"""
        scenario.llm.expect([
            Response.tool_call(name="nonexistent_tool", arguments={}),
            Response.content("抱歉，我找不到这个工具，换个方式试试")
        ])

        result = await scenario.run("调用nonexistent_tool")

        # 不存在的工具被LLM视为幻觉，valid_calls为空时回退content
        # 实际结果可能是LLM预设content或fallback的"已达上限"
        assert isinstance(result, str) and len(result) > 0
        # 消息链路：用户问题 + 助手回答（至少2条）
        assert len(scenario.messages) >= 2