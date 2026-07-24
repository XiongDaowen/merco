"""工具调用集成测试 — 端到端覆盖工具链路"""
import pytest

from merco.sandbox.guard import GuardAction, GuardConfirmationRequired
from merco.tools.base import BaseTool
from tests.integration.core.programmable_mock import Response


class BoomTool(BaseTool):
    name = "boom"
    description = "throws"
    toolset = "test"
    parameters = {"type": "object", "properties": {}}

    async def execute(self, **kwargs):
        raise RuntimeError("internal failure")


class TestToolCallChain:
    """工具调用完整链路测试"""

    @pytest.mark.asyncio
    async def test_single_tool_call_full_chain(self, scenario, tmp_path):
        """完整链路：用户提问 → LLM工具调用 → 工具执行 → 结果返回 → LLM综合回答"""
        # 创建测试文件
        test_file = tmp_path / "test.txt"
        test_file.write_text("hello world")

        # LLM先返回工具调用，然后根据工具返回结果回答
        scenario.provider.expect([
            Response.tool_call(
                name="read_file",
                arguments={"path": str(test_file)}
            ),
            Response.content("文件内容是：hello world")
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
        scenario.provider.expect([
            Response(
                tool_calls=[
                    {"id": "call_1", "name": "read_file", "arguments": {"path": str(file_a)}},
                    {"id": "call_2", "name": "read_file", "arguments": {"path": str(file_b)}},
                ]
            ),
            Response.content("两个文件内容分别是：content A 和 content B")
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
        scenario.provider.expect([
            Response.tool_call(name="nonexistent_tool", arguments={}),
            Response.content("抱歉，我找不到这个工具，换个方式试试")
        ])

        result = await scenario.run("调用nonexistent_tool")

        # 不存在的工具被LLM视为幻觉，valid_calls为空时回退content
        # 实际结果可能是LLM预设content或fallback的"已达上限"
        assert isinstance(result, str) and len(result) > 0
        # 消息链路：用户问题 + 助手回答（至少2条）
        assert len(scenario.messages) >= 2


class TestGuardIntegration:
    """Guard 中间件集成测试 — DENY / ASK / ALLOW"""

    @pytest.mark.asyncio
    async def test_guard_deny_blocks_tool(self, scenario):
        """DENY: 工具调用被守卫拒绝，LLM收到错误后调整回答"""
        scenario.set_guard_action("bash", GuardAction.DENY, reason="测试拒绝")

        scenario.provider.expect([
            Response.tool_call("bash", {"command": "ls"}),
            Response.content("操作被拒绝，尝试其他方式"),
        ])

        result = await scenario.run("列出文件")

        assert "拒绝" in result or "尝试其他方式" in result
        tool_msg = next(m for m in scenario.messages if m["role"] == "tool")
        assert "error" in tool_msg["content"]
        assert "测试拒绝" in tool_msg["content"]

    @pytest.mark.asyncio
    async def test_guard_ask_triggers_confirmation(self, scenario):
        """ASK: 守卫要求确认时抛出 GuardConfirmationRequired"""
        scenario.set_guard_action("bash", GuardAction.ASK, reason="需要确认")

        scenario.provider.expect([
            Response.tool_call("bash", {"command": "rm -rf /tmp/test"}),
        ])

        with pytest.raises(GuardConfirmationRequired):
            await scenario.run("删除测试目录")

    @pytest.mark.asyncio
    async def test_guard_allow_passes_through(self, scenario, tmp_path):
        """ALLOW: 守卫放行后工具正常执行，链路完整"""
        test_file = tmp_path / "ok.txt"
        test_file.write_text("ok")

        scenario.provider.expect([
            Response.tool_call("read_file", {"path": str(test_file)}),
            Response.content("读到了 ok"),
        ])

        result = await scenario.run("读文件")

        assert "ok" in result
        assert len(scenario.messages) == 4


class TestToolErrorHandling:
    @pytest.mark.asyncio
    async def test_tool_not_in_registry(self, scenario):
        """LLM 调用未注册的工具 → 被过滤为幻觉 → fallback 到预设 content"""
        scenario.provider.expect([
            Response.tool_call("nonexistent_tool", {}),
            Response.content("该工具不可用，我换个方式"),
        ])

        result = await scenario.run("调用不存在的工具")

        assert isinstance(result, str) and len(result) > 0
        # 不存在的工具被视为幻觉，valid_calls 为空时回退 content
        assert len(scenario.messages) >= 2

    @pytest.mark.asyncio
    async def test_tool_execution_exception(self, scenario):
        scenario.agent.tool_registry.register(BoomTool())

        scenario.provider.expect([
            Response.tool_call("boom", {}),
            Response.content("抱歉工具失败了"),
        ])

        result = await scenario.run("调一下 boom")

        assert "失败" in result
        tool_msg = next(m for m in scenario.messages if m["role"] == "tool")
        assert "internal failure" in tool_msg["content"]


class TestBuiltinToolsE2E:
    @pytest.fixture(autouse=True)
    def _use_real_tools(self, scenario):
        """e2e 测试用真实工具替换 mock 工具"""
        from merco.tools.bash_tools import BashTool
        from merco.tools.edit import EditFile
        from merco.tools.file_tools import ReadFile, WriteFile

        # 注销 mock 工具
        for name in ("read_file", "write_file", "bash", "edit_file"):
            scenario.agent.tool_registry.unregister(name)

        # 注册真实工具
        scenario.agent.tool_registry.register(ReadFile())
        scenario.agent.tool_registry.register(WriteFile())
        scenario.agent.tool_registry.register(BashTool())
        scenario.agent.tool_registry.register(EditFile())

    @pytest.mark.asyncio
    async def test_write_file_creates_file(self, scenario):
        target = scenario.tmp_path / "new.txt"
        scenario.provider.expect([
            Response.tool_call("write_file", {"path": str(target), "content": "hello"}),
            Response.content("已创建文件"),
        ])

        await scenario.run("写一个新文件")

        assert target.exists()
        assert target.read_text() == "hello"

    @pytest.mark.asyncio
    async def test_edit_file_modifies_content(self, scenario, monkeypatch):
        target = scenario.tmp_path / "code.py"
        target.write_text("def foo():\n    return 1\n")

        # auto-confirm 跳过交互式确认（confirm_edit 是 async 的）
        async def _auto_confirm(*a, **kw):
            return True

        monkeypatch.setattr("merco.tools.middleware.confirm_edit", _auto_confirm)

        scenario.provider.expect([
            Response.tool_call("edit_file", {
                "path": str(target),
                "search": "return 1",
                "replace": "return 42",
            }),
            Response.content("已修改"),
        ])

        await scenario.run("把 return 1 改成 return 42")

        content = target.read_text()
        assert "return 42" in content
        assert "return 1" not in content

    @pytest.mark.asyncio
    async def test_bash_executes_real_command(self, scenario):
        out_file = scenario.tmp_path / "out.txt"
        scenario.provider.expect([
            Response.tool_call("bash", {"command": f"echo test > {out_file}"}),
            Response.content("命令已执行"),
        ])

        await scenario.run("写一个测试文件")

        assert out_file.exists()
        assert out_file.read_text().strip() == "test"
