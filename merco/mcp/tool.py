"""MCP tool → BaseTool adapter for ToolRegistry."""
from merco.tools.base import BaseTool


class MCPServerTool(BaseTool):
    """Adapt an MCP tool spec to a merco ToolRegistry-compatible tool."""

    def __init__(self, mcp_spec: dict, server_name: str, handler, guard=None):
        self.name = mcp_spec.get("name", "unknown")
        self.description = mcp_spec.get("description", f"MCP tool from {server_name}")
        self.toolset = f"mcp:{server_name}"
        self.server = server_name
        self._input_schema = mcp_spec.get("inputSchema", {})
        self._handler = handler  # async (tool_name, arguments) -> dict
        self._guard = guard

    @property
    def parameters(self) -> dict:
        return self._input_schema

    async def execute(self, **kwargs) -> dict:
        """Execute via handler. Guard checked by MCPServerManager before this."""
        try:
            return await self._handler(self.name, kwargs)
        except Exception as e:
            return {"error": f"{self.name}: {e}", "isError": True}

    def check(self) -> bool:
        return self._handler is not None

    def get_definition(self, context=None) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self._input_schema,
            },
        }
