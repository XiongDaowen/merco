"""Agent 核心循环集成测试"""

import pytest
from openmercury.core.config import OpenMercuryConfig, ModelConfig
from openmercury.tools.registry import ToolRegistry
from openmercury.tools.base import BaseTool


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
        cfg = OpenMercuryConfig()
        assert cfg.model.provider == "openai"
        assert cfg.model.model == "gpt-4"

    def test_config_with_model(self):
        cfg = OpenMercuryConfig()
        cfg.model.model = "claude-3"
        cfg.model.provider = "anthropic"
        assert cfg.model.model == "claude-3"


class TestToolRegistry:
    def test_register_and_execute(self):
        registry = ToolRegistry()
        registry.register(MockTool())

        import asyncio
        result = asyncio.get_event_loop().run_until_complete(
            registry.execute("echo", message="hello")
        )
        assert result["echo"] == "hello"

    def test_tool_not_found(self):
        registry = ToolRegistry()

        import asyncio
        result = asyncio.get_event_loop().run_until_complete(
            registry.execute("nonexistent")
        )
        assert "error" in result
