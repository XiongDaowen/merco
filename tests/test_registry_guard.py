"""ToolRegistry 与 ToolGuard 集成测试"""

import asyncio
import sys
import pytest

sys.path.insert(0, ".")

# 导入工具模块以注册工具到 tool_registry 单例
from merco.tools import bash_tools  # noqa: F401
from merco.tools import file_tools  # noqa: F401
from merco.tools import edit  # noqa: F401

from merco.sandbox.guard import ToolGuard, GuardResult, GuardAction, GuardConfirmationRequired
from merco.tools.middleware import GuardMiddleware
from merco.tools.registry import tool_registry


@pytest.fixture
def registry():
    """使用模块级工具注册表单例"""
    return tool_registry


@pytest.mark.asyncio
async def test_registry_calls_guard(registry):
    """Registry.execute 调用 ToolGuard"""
    from unittest.mock import AsyncMock

    # Mock 一个工具（临时注册）
    class MockTool:
        name = "mock_tool_test"
        description = "mock"
        toolset = "test"
        parameters = {"type": "object", "properties": {}}
        execute = AsyncMock(return_value={"result": "ok"})

    registry.register(MockTool())

    mock_guard = AsyncMock()
    mock_guard.check = AsyncMock(return_value=GuardResult(action=GuardAction.ALLOW, command=""))

    mw = GuardMiddleware(mock_guard)
    idx = registry._middleware.use(mw)
    try:
        result = await registry.execute("mock_tool_test")

        mock_guard.check.assert_called_once_with("mock_tool_test", {})
        assert "error" not in result
    finally:
        registry.unregister("mock_tool_test")
        registry._middleware._middlewares.remove(mw)


@pytest.mark.asyncio
async def test_registry_blocks_when_guard_denies(registry):
    """Guard 拒绝时 Registry 返回错误，不执行工具"""
    from unittest.mock import AsyncMock

    class MockTool:
        name = "mock_tool_deny"
        description = "mock"
        toolset = "test"
        parameters = {"type": "object", "properties": {}}
        execute = AsyncMock(return_value={"result": "ok"})

    registry.register(MockTool())

    mock_guard = AsyncMock()
    mock_guard.check = AsyncMock(return_value=GuardResult(
        action=GuardAction.DENY, command="", reason="测试拒绝",
    ))

    mw = GuardMiddleware(mock_guard)
    registry._middleware.use(mw)
    tool = MockTool()
    try:
        result = await registry.execute("mock_tool_deny")

        # 工具不应被执行
        tool.execute.assert_not_awaited()
        # 应返回拦截错误
        assert "error" in result
        assert "安全守卫拒绝" in result["error"]
    finally:
        registry.unregister("mock_tool_deny")
        registry._middleware._middlewares.remove(mw)


@pytest.mark.asyncio
async def test_registry_dangerous_command_asks(registry):
    """危险命令 rm -rf / 触发 ASK 确认"""
    from unittest.mock import AsyncMock

    mock_guard = AsyncMock()
    mock_guard.check = AsyncMock(return_value=GuardResult(
        action=GuardAction.ASK, command="rm -rf /", reason="危险命令",
    ))

    mw = GuardMiddleware(mock_guard)
    registry._middleware.use(mw)
    try:
        with pytest.raises(GuardConfirmationRequired):
            await registry.execute("bash", command="rm -rf /")
    finally:
        registry._middleware._middlewares.remove(mw)


@pytest.mark.asyncio
async def test_registry_safe_command_allowed(registry):
    """安全命令 ls 放行"""
    result = await registry.execute("bash", command="ls -la")
    # ls 是安全命令，应返回 ALLOW
    assert result.get("returncode") == 0 or "error" not in result


@pytest.mark.asyncio
async def test_registry_path_traversal_blocked(registry):
    """路径穿越被拦截"""
    from unittest.mock import AsyncMock

    mock_guard = AsyncMock()
    mock_guard.check = AsyncMock(return_value=GuardResult(
        action=GuardAction.DENY, command="../../../etc/passwd", reason="路径穿越",
    ))

    mw = GuardMiddleware(mock_guard)
    registry._middleware.use(mw)
    try:
        result = await registry.execute("write_file", path="../../../etc/passwd", content="x")

        assert "error" in result
        assert "安全守卫" in result["error"]
    finally:
        registry._middleware._middlewares.remove(mw)


@pytest.mark.asyncio
async def test_registry_system_path_blocked(registry):
    """系统路径访问被拦截"""
    from unittest.mock import AsyncMock

    mock_guard = AsyncMock()
    mock_guard.check = AsyncMock(return_value=GuardResult(
        action=GuardAction.DENY, command="/proc/cpuinfo", reason="系统路径",
    ))

    mw = GuardMiddleware(mock_guard)
    registry._middleware.use(mw)
    try:
        result = await registry.execute("read_file", path="/proc/cpuinfo")

        assert "error" in result
        assert "安全守卫" in result["error"]
    finally:
        registry._middleware._middlewares.remove(mw)


@pytest.mark.asyncio
async def test_registry_auto_mode_bypasses(registry):
    """sandbox_mode=auto 跳过所有确认"""
    from unittest.mock import patch

    auto_guard = ToolGuard(mode="auto")

    with patch("merco.sandbox.tool_guard", auto_guard):
        result = await registry.execute("bash", command="rm -rf /")

    # auto 模式返回 ALLOW，命令被放行
    assert "error" not in result or result.get("returncode") == 0


@pytest.mark.asyncio
async def test_registry_unknown_tool_error(registry):
    """不存在的工具返回错误"""
    result = await registry.execute("nonexistent_tool", foo="bar")
    assert "error" in result
    assert "不存在" in result["error"]
