"""Tests for MCPServerTool adapter."""
import pytest
from merco.mcp.tool import MCPServerTool


class TestMCPServerTool:
    """Tests for MCPServerTool — adapting MCP tool specs to BaseTool."""

    def test_mcp_tool_name_and_toolset(self):
        """Create with spec, verify name/toolset/server."""
        spec = {
            "name": "fetch_url",
            "description": "Fetch a URL and return its content",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to fetch"}
                },
                "required": ["url"],
            },
        }
        tool = MCPServerTool(spec, server_name="my-server", handler=None)

        assert tool.name == "fetch_url"
        assert tool.toolset == "mcp:my-server"
        assert tool.server == "my-server"
        assert tool.description == "Fetch a URL and return its content"
        assert tool.parameters == spec["inputSchema"]

    def test_mcp_tool_defaults_from_spec(self):
        """When spec is missing fields, fall back to defaults."""
        spec = {}
        tool = MCPServerTool(spec, server_name="defaults", handler=None)

        assert tool.name == "unknown"
        assert tool.description == "MCP tool from defaults"
        assert tool.toolset == "mcp:defaults"
        assert tool.parameters == {}

    @pytest.mark.asyncio
    async def test_mcp_tool_execute(self):
        """Mock handler returns result, verify execute() calls handler."""
        async def handler(tool_name, arguments):
            return {"result": f"ran {tool_name} with {arguments}"}

        spec = {"name": "echo", "description": "Echoes input", "inputSchema": {}}
        tool = MCPServerTool(spec, server_name="test", handler=handler)

        result = await tool.execute(message="hello")
        assert result == {"result": "ran echo with {'message': 'hello'}"}

    @pytest.mark.asyncio
    async def test_mcp_tool_execute_error(self):
        """Handler raises, verify returns error dict."""
        async def handler(tool_name, arguments):
            raise ValueError("something went wrong")

        spec = {"name": "broken", "description": "Always fails", "inputSchema": {}}
        tool = MCPServerTool(spec, server_name="test", handler=handler)

        result = await tool.execute()
        assert result["isError"] is True
        assert "broken: something went wrong" in result["error"]

    def test_mcp_tool_check(self):
        """Verify check() returns True when handler set, False otherwise."""
        tool_with_handler = MCPServerTool({}, "s", handler=lambda: None)
        tool_without_handler = MCPServerTool({}, "s", handler=None)

        assert tool_with_handler.check() is True
        assert tool_without_handler.check() is False

    def test_mcp_tool_definition(self):
        """Verify get_definition format matches OpenAI function calling."""
        spec = {
            "name": "search_docs",
            "description": "Search documentation",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"}
                },
            },
        }
        tool = MCPServerTool(spec, server_name="docs", handler=None)
        definition = tool.get_definition()

        assert definition["type"] == "function"
        assert definition["function"]["name"] == "search_docs"
        assert definition["function"]["description"] == "Search documentation"
        assert definition["function"]["parameters"] == spec["inputSchema"]

    def test_mcp_tool_definition_accepts_context(self):
        """get_definition accepts optional context and ignores it."""
        tool = MCPServerTool(
            {"name": "x", "description": "desc", "inputSchema": {}},
            "s",
            handler=None,
        )
        definition = tool.get_definition(context={"skills": ["a", "b"]})
        assert definition["type"] == "function"
