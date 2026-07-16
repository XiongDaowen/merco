"""commands.py 全部斜杠命令输出测试"""
import pytest
from unittest.mock import MagicMock, AsyncMock

from cli import commands
from tests.cli.conftest import make_fake_agent


# ─────────── INFO GROUP ───────────

@pytest.mark.asyncio
async def test_help_renders_panel_with_help_text(capture_console):
    """/help 渲染 Panel 含帮助文本；Panel 渲染到 markup foo 对象，文本用 export_text 验证"""
    capture, buf, markup = capture_console
    await commands.cmd_help(make_fake_agent(), "")
    text = capture.export_text()
    assert "帮助" in text
    assert "/help" in text or "/tools" in text or "/sessions" in text


@pytest.mark.asyncio
async def test_model_command_shows_provider_and_model(capture_console):
    """/model 显示 provider/model — 直接 markup 字符串，不含 Panel"""
    capture, buf, markup = capture_console
    await commands.cmd_model(make_fake_agent(), "")
    text = buf.getvalue()
    assert "当前模型" in text
    assert "openai" in text
    assert "gpt-4o" in text


@pytest.mark.asyncio
async def test_context_command_renders_bar_and_threshold(capture_console):
    """/context 输出进度条和阈值"""
    capture, buf, markup = capture_console
    agent = make_fake_agent()
    agent.get_context_stats = MagicMock(return_value={
        "ratio": 0.3, "threshold": 0.8, "current": 300, "max": 1000,
        "is_estimate": False,
    })
    await commands.cmd_context(agent, "")
    text = capture.export_text()
    assert "阈值" in text
    assert "80%" in text
    assert "否（API 实测）" in text


@pytest.mark.asyncio
async def test_context_command_shows_estimate_label(capture_console):
    """is_estimate=True 时显示'是'"""
    capture, buf, markup = capture_console
    agent = make_fake_agent()
    agent.get_context_stats = MagicMock(return_value={
        "ratio": 0.0, "threshold": 0.8, "current": 0, "max": 1000,
        "is_estimate": True,
    })
    await commands.cmd_context(agent, "")
    text = buf.getvalue()
    assert "是" in text


# ─────────── TOOLS ───────────

@pytest.mark.asyncio
async def test_tools_no_tools_shows_message(capture_console):
    """/tools 0 工具时显示'无可用工具'"""
    capture, buf, markup = capture_console
    agent = make_fake_agent()
    agent.tool_registry = None
    await commands.cmd_tools(agent, "")
    text = buf.getvalue()
    assert "无可用工具" in text


@pytest.mark.asyncio
async def test_tools_lists_builtin_tools(capture_console):
    """/tools 列出内置工具"""
    capture, buf, markup = capture_console
    agent = make_fake_agent()
    registry = MagicMock()
    t1 = MagicMock()
    t1.name = "read_file"
    t1.check = MagicMock(return_value=True)
    t1.toolset = "builtin"
    t1.description = "读取文件"
    t2 = MagicMock()
    t2.name = "write_file"
    t2.check = MagicMock(return_value=True)
    t2.toolset = "builtin"
    t2.description = "写入文件"
    registry.list_tools = MagicMock(return_value=[t1, t2])
    agent.tool_registry = registry
    await commands.cmd_tools(agent, "")
    text = buf.getvalue()
    assert "可用工具" in text
    assert "read_file" in text
    assert "write_file" in text


@pytest.mark.asyncio
async def test_tools_lists_mcp_tools_with_prefix(capture_console):
    """/tools 显示 MCP 工具，前缀 mcp:xxx"""
    capture, buf, markup = capture_console
    agent = make_fake_agent()
    registry = MagicMock()
    t = MagicMock()
    t.name = "mcp_tool_a"
    t.check = MagicMock(return_value=True)
    t.toolset = "mcp:filesystem"
    t.description = "MCP 工具"
    registry.list_tools = MagicMock(return_value=[t])
    agent.tool_registry = registry
    await commands.cmd_tools(agent, "")
    text = buf.getvalue()
    assert "mcp:filesystem" in text
    assert "mcp_tool_a" in text


@pytest.mark.asyncio
async def test_tools_skips_inactive(capture_console):
    """/tools 不显示 check()=False 的工具"""
    capture, buf, markup = capture_console
    agent = make_fake_agent()
    registry = MagicMock()
    t_active = MagicMock()
    t_active.name = "active_tool"
    t_active.check = MagicMock(return_value=True)
    t_active.toolset = "builtin"
    t_active.description = "active"
    t_inactive = MagicMock()
    t_inactive.name = "inactive_tool"
    t_inactive.check = MagicMock(return_value=False)
    t_inactive.toolset = "builtin"
    t_inactive.description = "inactive"
    registry.list_tools = MagicMock(return_value=[t_active, t_inactive])
    agent.tool_registry = registry
    await commands.cmd_tools(agent, "")
    text = buf.getvalue()
    assert "active_tool" in text
    assert "inactive_tool" not in text


# ─────────── REPORT / RELOAD-MCP / MCP-STATUS ───────────

@pytest.mark.asyncio
async def test_report_renders_session_report_panel(capture_console):
    """/report 渲染 Session Report Panel"""
    capture, buf, markup = capture_console
    await commands.cmd_report(make_fake_agent(), "")
    text = capture.export_text()
    assert "📊 Session Report" in text
    assert "report content" in text


@pytest.mark.asyncio
async def test_report_reset_clears_and_shows_dim_message(capture_console):
    """/report reset 显示[dim]统计数据已清零[/dim] — 用 markup 验证 dim 标签"""
    capture, buf, markup = capture_console
    agent = make_fake_agent()
    await commands.cmd_report(agent, "reset")
    assert "[dim]统计数据已清零[/dim]" in capture.get_markup()
    agent.observer.reset.assert_called_once()


@pytest.mark.asyncio
async def test_reload_mcp_not_initialized(capture_console):
    """/reload-mcp 在 mcp_manager 缺失时显示提示并 return True"""
    capture, buf, markup = capture_console
    agent = make_fake_agent()
    del agent.mcp_manager  # MagicMock auto-creates attr; force removal
    result = await commands.cmd_reload_mcp(agent, "")
    assert "[dim]MCP 尚未初始化[/dim]" in capture.get_markup()
    assert result is True


@pytest.mark.asyncio
async def test_reload_mcp_success_shows_server_count(capture_console):
    """/reload-mcp 成功时显示 server 数"""
    capture, buf, markup = capture_console
    agent = make_fake_agent()
    mcp = MagicMock()
    mcp.reload = AsyncMock()
    mcp.status = MagicMock(return_value={
        "fs": {"tools_count": 5},
        "git": {"tools_count": 3},
    })
    agent.mcp_manager = mcp
    await commands.cmd_reload_mcp(agent, "")
    text = capture.export_text()
    assert "MCP 已重载" in text
    assert "fs" in text
    assert "5 tools" in text


@pytest.mark.asyncio
async def test_mcp_status_not_initialized(capture_console):
    """/mcp-status 在 mcp_manager 缺失时显示提示"""
    capture, buf, markup = capture_console
    agent = make_fake_agent()
    del agent.mcp_manager
    await commands.cmd_mcp_status(agent, "")
    assert "[dim]MCP 尚未初始化[/dim]" in capture.get_markup()


@pytest.mark.asyncio
async def test_mcp_status_empty(capture_console):
    """/mcp-status 无连接服务器时显示提示"""
    capture, buf, markup = capture_console
    agent = make_fake_agent()
    agent.mcp_manager.status = MagicMock(return_value={})
    await commands.cmd_mcp_status(agent, "")
    assert "[dim]无已连接的 MCP 服务器[/dim]" in capture.get_markup()


@pytest.mark.asyncio
async def test_mcp_status_lists_with_icon(capture_console):
    """/mcp-status 列出服务器，🟢 / 🔴 按 connected 状态切换"""
    capture, buf, markup = capture_console
    agent = make_fake_agent()
    agent.mcp_manager.status = MagicMock(return_value={
        "ok": {"connected": True, "tools_count": 5},
        "bad": {"connected": False, "tools_count": 0},
    })
    await commands.cmd_mcp_status(agent, "")
    text = buf.getvalue()
    assert "🟢 ok" in text
    assert "🔴 bad" in text
    assert "MCP 服务器状态" in text


# ─────────── SESSIONS ───────────

@pytest.mark.asyncio
async def test_sessions_empty(capture_console):
    """/sessions 无历史时 [dim]无历史会话[/dim]"""
    capture, buf, markup = capture_console
    agent = make_fake_agent()
    agent._session_store.list_sessions = MagicMock(return_value=[])
    await commands.cmd_sessions(agent, "")
    assert "[dim]无历史会话[/dim]" in capture.get_markup()


@pytest.mark.asyncio
async def test_sessions_lists_with_index_and_marker(capture_console):
    """/sessions 列出历史，当前会话标记 ← 当前"""
    capture, buf, markup = capture_console
    agent = make_fake_agent()
    agent._session_store.list_sessions = MagicMock(return_value=[
        {"id": "abc", "title": "历史 1", "message_count": 5, "updated_at": "2026-07-16T10:00:00"},
        {"id": "test-session-id", "title": "测试会话", "message_count": 3, "updated_at": "2026-07-16T11:00:00"},
    ])
    await commands.cmd_sessions(agent, "")
    text = capture.export_text()
    assert "📋 历史会话" in text
    assert "历史 1" in text
    assert "测试会话" in text
    assert "← 当前" in text


@pytest.mark.asyncio
async def test_sessions_switch_invalid_index(capture_console):
    """/sessions 999 显示'无效的会话序号'红字"""
    capture, buf, markup = capture_console
    agent = make_fake_agent()
    agent._session_store.list_sessions = MagicMock(return_value=[
        {"id": "abc", "title": "a", "message_count": 0, "updated_at": "2026-07-16T10:00:00"},
    ])
    await commands.cmd_sessions(agent, "999")
    assert "[red]无效的会话序号[/red]" in capture.get_markup()


@pytest.mark.asyncio
async def test_sessions_switch_same_session(capture_console):
    """/sessions 切到当前会话显示[dim]已经是当前会话[/dim]"""
    capture, buf, markup = capture_console
    agent = make_fake_agent()
    agent._session_store.list_sessions = MagicMock(return_value=[
        {"id": "test-session-id", "title": "测试会话", "message_count": 3, "updated_at": "2026-07-16T11:00:00"},
    ])
    await commands.cmd_sessions(agent, "1")
    assert "[dim]已经是当前会话[/dim]" in capture.get_markup()


# ─────────── EXIT / FORK ───────────

@pytest.mark.asyncio
async def test_exit_command_returns_false_and_prints_goodbye(capture_console):
    """/exit 返回 False 以终止 REPL，[dim]再见！[/dim]"""
    capture, buf, markup = capture_console
    result = await commands.cmd_exit(make_fake_agent(), "")
    assert "[dim]再见！[/dim]" in capture.get_markup()
    assert result is False


@pytest.mark.asyncio
async def test_fork_success_shows_green(capture_console):
    """/fork 成功显示 green 提示 使用 patch 接管 Session.fork"""
    capture, buf, markup = capture_console
    from unittest.mock import patch
    from merco.core.session import Session

    agent = make_fake_agent()
    new_session = MagicMock()
    new_session.id = "new-id-12345678"
    new_session.title = "新分支"

    with patch.object(Session, "fork", return_value=new_session):
        await commands.cmd_fork(agent, "新分支")
    text = buf.getvalue()
    assert "已 fork 到" in text


@pytest.mark.asyncio
async def test_fork_failure_shows_red(capture_console):
    """/fork 失败显示 red 提示"""
    capture, buf, markup = capture_console
    from unittest.mock import patch
    from merco.core.session import Session

    agent = make_fake_agent()
    with patch.object(Session, "fork", return_value=None):
        await commands.cmd_fork(agent, "失败分支")
    assert "[red]Fork 失败[/red]" in capture.get_markup()
