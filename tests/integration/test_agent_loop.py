"""Agent 核心循环集成测试"""

from merco.core.config import MercoConfig
from merco.tools.base import BaseTool
from merco.tools.registry import ToolRegistry


class MockTool(BaseTool):
    """模拟工具用于测试"""
    name = "echo"
    description = "回显参数"
    parameters = {
        "type": "object",
        "properties": {
            "message": {"type": "string", "description": "要回显的消息"},
        },
        "required": ["message"],
    }

    async def execute(self, message: str, **kwargs):
        return {"echo": message}


class TestAgentConfig:
    def test_default_config(self):
        cfg = MercoConfig()
        assert cfg.model.provider == "openai"
        assert cfg.model.model == "gpt-4"

    def test_config_with_model(self):
        cfg = MercoConfig()
        cfg.model.model = "claude-3"
        cfg.model.provider = "anthropic"
        assert cfg.model.model == "claude-3"


class TestToolRegistry:
    def test_register_and_execute(self):
        registry = ToolRegistry()
        registry.register(MockTool())

        import asyncio
        result = asyncio.run(
            registry.execute("echo", message="hello")
        )
        assert result["echo"] == "hello"

    def test_tool_not_found(self):
        registry = ToolRegistry()

        import asyncio
        result = asyncio.run(
            registry.execute("nonexistent")
        )
        assert "error" in result
