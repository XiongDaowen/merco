"""MCP 工具集成"""

from .base import BaseTool


class MCPTool(BaseTool):
    """MCP 服务器工具调用"""

    name = "mcp_call"
    description = "调用已连接的 MCP 服务器工具"
    toolset = "mcp"
    parameters = {
        "type": "object",
        "properties": {
            "server": {"type": "string", "description": "MCP 服务器名称"},
            "tool": {"type": "string", "description": "工具名称"},
            "arguments": {"type": "object", "description": "工具参数"},
        },
        "required": ["server", "tool"],
    }

    def check(self) -> bool:
        """MCP 客户端未实现时隐藏此工具"""
        return False  # TODO: 实现后改为 True

    async def execute(self, server: str, tool: str, arguments: dict = None) -> dict:
        # TODO: 实现 MCP 客户端
        return {
            "error": "MCP integration not yet configured",
            "server": server,
            "tool": tool,
        }


from .registry import tool_registry  # noqa: E402 — 模块末尾自注册
tool_registry.register(MCPTool())


class MCPManager:
    """MCP 服务器管理器"""

    def __init__(self):
        self._servers = {}

    async def connect(self, name: str, config: dict):
        """连接 MCP 服务器"""
        raise NotImplementedError

    async def disconnect(self, name: str):
        """断开 MCP 服务器"""
        raise NotImplementedError

    def list_servers(self) -> list:
        """列出已连接的服务器"""
        return list(self._servers.keys())
