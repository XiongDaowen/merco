"""ToolRegistry 与 ToolGuard 集成测试"""

import asyncio
import sys
import pytest

sys.path.insert(0, ".")

# 导入工具模块以注册工具到 tool_registry 单例
from merco.tools import bash_tools  # noqa: F401
from merco.tools import file_tools  # noqa: F401
from merco.tools import edit  # noqa: F401

from merco.sandbox.guard import ToolGuard
from merco.tools.registry import tool_registry


@pytest.fixture
def registry():
    """使用模块级工具注册表单例"""
    return tool_registry


@pytest.fixture
def mock_confirm_allow():
    """模拟用户确认"""
    async def mock(self, command, rule):
        return True
    original = ToolGuard._confirm
    ToolGuard._confirm = mock
    yield
    ToolGuard._confirm = original


@pytest.fixture
def mock_confirm_deny():
    """模拟用户拒绝"""
    async def mock(self, command, rule):
        return False
    original = ToolGuard._confirm
    ToolGuard._confirm = mock
    yield
    ToolGuard._confirm = original


@pytest.mark.asyncio
async def test_registry_calls_guard(mock_confirm_allow, registry):
    """Registry.execute 调用 ToolGuard"""
    from unittest.mock import AsyncMock, patch

    # Mock 一个工具（临时注册）
    class MockTool:
        name = "mock_tool_test"
        description = "mock"
        toolset = "test"
        parameters = {"type": "object", "properties": {}}
        execute = AsyncMock(return_value={"result": "ok"})

    registry.register(MockTool())

    try:
        with patch("merco.sandbox.tool_guard") as mock_guard:
            mock_guard.check = AsyncMock(return_value=True)
            result = await registry.execute("mock_tool_test")

        mock_guard.check.assert_called_once_with("mock_tool_test", {})
        MockTool().execute.assert_awaited_once()
    finally:
        registry.unregister("mock_tool_test")


@pytest.mark.asyncio
async def test_registry_blocks_when_guard_denies(registry):
    """Guard 拒绝时 Registry 返回错误，不执行工具"""
    from unittest.mock import AsyncMock, patch

    class MockTool:
        name = "mock_tool_deny"
        description = "mock"
        toolset = "test"
        parameters = {"type": "object", "properties": {}}
        execute = AsyncMock(return_value={"result": "ok"})

    registry.register(MockTool())

    try:
        with patch("merco.sandbox.tool_guard") as mock_guard:
            mock_guard.check = AsyncMock(return_value=False)
            result = await registry.execute("mock_tool_deny")

        # 工具不应被执行
        MockTool().execute.assert_not_awaited()
        # 应返回拦截错误
        assert "error" in result
        assert "安全守卫拦截" in result["error"]
    finally:
        registry.unregister("mock_tool_deny")


@pytest.mark.asyncio
async def test_registry_dangerous_command_blocked(registry):
    """危险命令 rm -rf / 被拦截"""
    async def mock_reject(command, rule):
        return False
    original = ToolGuard._confirm
    ToolGuard._confirm = mock_reject

    try:
        result = await registry.execute("bash", command="rm -rf /")
        assert "error" in result
        assert "安全守卫拦截" in result["error"]
    finally:
        ToolGuard._confirm = original


@pytest.mark.asyncio
async def test_registry_safe_command_allowed(mock_confirm_allow, registry):
    """安全命令 ls 放行"""
    result = await registry.execute("bash", command="ls -la")
    # ls 是安全命令，_check 返回 True
    assert result.get("returncode") == 0 or "error" not in result


@pytest.mark.asyncio
async def test_registry_path_traversal_blocked(registry):
    """路径穿越被拦截"""
    result = await registry.execute("write_file", path="../../../etc/passwd", content="x")

    assert "error" in result
    assert "安全守卫拦截" in result["error"]


@pytest.mark.asyncio
async def test_registry_system_path_blocked(registry):
    """系统路径访问被拦截"""
    result = await registry.execute("read_file", path="/proc/cpuinfo")

    assert "error" in result
    assert "安全守卫拦截" in result["error"]


@pytest.mark.asyncio
async def test_registry_auto_mode_bypasses(mock_confirm_allow, registry):
    """sandbox_mode=auto 跳过所有确认"""
    from unittest.mock import patch

    auto_guard = ToolGuard(mode="auto")

    with patch("merco.sandbox.tool_guard", auto_guard):
        result = await registry.execute("bash", command="rm -rf /")

    assert result.get("returncode") == 0 or "error" not in result


@pytest.mark.asyncio
async def test_registry_unknown_tool_error(registry):
    """不存在的工具返回错误"""
    result = await registry.execute("nonexistent_tool", foo="bar")
    assert "error" in result
    assert "不存在" in result["error"]