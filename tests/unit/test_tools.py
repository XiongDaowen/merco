"""工具注册测试"""

from merco.tools.base import BaseTool
from merco.tools.registry import ToolRegistry


class MockTool(BaseTool):
    name = "mock_tool"
    description = "A mock tool for testing"
    parameters = {"type": "object", "properties": {}}

    async def execute(self, **kwargs):
        return {"result": "success"}


class TestToolRegistry:
    def test_register_tool(self):
        registry = ToolRegistry()
        tool = MockTool()
        registry.register(tool)
        assert registry.get("mock_tool") == tool

    def test_list_tools(self):
        registry = ToolRegistry()
        registry.register(MockTool())
        tools = registry.list_tools()
        assert len(tools) == 1

    def test_get_definitions(self):
        registry = ToolRegistry()
        registry.register(MockTool())
        defs = registry.get_definitions()
        assert len(defs) == 1
        assert defs[0]["function"]["name"] == "mock_tool"
