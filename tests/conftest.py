"""集成测试共享工厂 — Mock LLM + Agent Fixture"""

import pytest

# 直导避免触发 openai 依赖
import sys, os as _os
_merco = _os.path.join(_os.path.dirname(__file__), "..")
if _merco not in sys.path:
    sys.path.insert(0, _merco)

from merco.core.config import MercoConfig      # noqa: E402
from merco.core.agent import Agent              # noqa: E402
from merco.core.llm.base import ModelProvider   # noqa: E402

from merco.tools.registry import ToolRegistry    # noqa: E402
from merco.tools.base import BaseTool            # noqa: E402
from merco.tools.skill_tools import SkillViewTool  # noqa: E402


from merco.tools.task_tools import TaskTool  # noqa: E402


# ── 内置测试工具 ──────────────────────────────────────────

class MockEchoTool(BaseTool):
    name = "echo"
    description = "回显参数"
    toolset = "test"
    parameters = {
        "type": "object",
        "properties": {
            "message": {"type": "string", "description": "要回显的消息"},
        },
        "required": ["message"],
    }

    async def execute(self, message: str, **kwargs):
        return {"echo": message}


class MockReadTool(BaseTool):
    name = "read_file"
    description = "读取文件"
    toolset = "test"
    parameters = {
        "type": "object",
        "properties": {"path": {"type": "string"}},
        "required": ["path"],
    }

    async def execute(self, path: str, **kwargs):
        return {"content": f"mock content of {path}", "start_line": 1, "end_line": 1}


class MockBashTool(BaseTool):
    name = "bash"
    description = "执行命令"
    toolset = "test"
    parameters = {
        "type": "object",
        "properties": {"command": {"type": "string"}},
        "required": ["command"],
    }

    async def execute(self, command: str, **kwargs):
        return {"stdout": f"mock: {command}", "stderr": "", "returncode": 0}


class MockEditTool(BaseTool):
    name = "edit_file"
    description = "编辑文件"
    toolset = "test"
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "search": {"type": "string"},
            "replace": {"type": "string"},
        },
        "required": ["path", "search", "replace"],
    }

    async def execute(self, path: str, search: str, replace: str, **kwargs):
        return {"success": True, "path": path, "message": "modified"}


def make_test_registry() -> ToolRegistry:
    reg = ToolRegistry()
    reg.register(MockEchoTool())
    reg.register(MockReadTool())
    reg.register(MockBashTool())
    reg.register(MockEditTool())
    reg.register(SkillViewTool())
    reg.register(TaskTool())
    return reg


# ── Mock ModelProvider ─────────────────────────────────────

class MockModelProvider(ModelProvider):
    """按顺序消费预设响应，记录每次调用。"""

    name = "mock"

    def __init__(self, responses: list[dict] | None = None, **kwargs):
        self.responses = list(responses or [])
        self.calls: list[dict] = []  # {messages, tools} per call

    async def chat(self, messages: list[dict], tools: list[dict] = None,
                   tool_choice: str = "auto") -> dict:
        self.calls.append({"messages": messages, "tools": tools})
        if not self.responses:
            return {"content": "", "finish_reason": "stop"}
        resp = dict(self.responses.pop(0))
        if "content" not in resp:
            resp["content"] = ""
        return resp

    async def chat_stream(self, messages: list[dict], tools: list[dict] = None,
                          tool_choice: str = "auto"):
        resp = await self.chat(messages, tools, tool_choice)
        yield resp


# ── Test Agent Factory ────────────────────────────────────

@pytest.fixture
async def test_agent(monkeypatch, tmp_path):
    """创建带有 mock provider + 测试工具 + 临时 session store 的 Agent"""
    db_path = str(tmp_path / "test.db")

    # Mock _get_db_path，让 Agent 使用临时目录
    monkeypatch.setattr("merco.core.agent._get_db_path", lambda: db_path)

    cfg = MercoConfig()
    cfg.model.api_key = "test-key"
    cfg.model.model = "test-model"
    cfg.sandbox_mode = "auto"
    cfg.memory_path = str(tmp_path / "memory")  # 隔离 memory 目录，不污染 ~/.merco/memory

    reg = make_test_registry()
    agent = await Agent.create(config=cfg, tool_registry=reg)
    # 注入默认空 mock provider，避免触发真实 registry 解析
    agent.provider = MockModelProvider()
    return agent
