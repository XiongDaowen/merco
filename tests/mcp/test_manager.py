"""Tests for MCPServerManager lifecycle."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from merco.mcp.config import MCPServerConfig
from merco.mcp.manager import MCPServerManager
from merco.mcp.tool import MCPServerTool
from merco.tools.registry import ToolRegistry


class TestMCPServerManager:
    """Tests for MCPServerManager — connect/discover/register lifecycle."""

    @pytest.fixture
    def registry(self):
        return ToolRegistry()

    @pytest.fixture
    def hooks(self):
        h = MagicMock()
        h.emit = AsyncMock()
        return h

    @pytest.fixture
    def manager(self, registry, hooks):
        return MCPServerManager(tool_registry=registry, hooks=hooks)

    # --- load_config tests ---

    @pytest.mark.asyncio
    async def test_load_config_skips_disabled(self, manager):
        """Config with enabled=false → no connect call."""
        config = {"server-a": {"command": "echo", "enabled": False}}

        with patch.object(manager, "connect", new_callable=AsyncMock) as mock_connect:
            await manager.load_config(config)

        mock_connect.assert_not_called()

    @pytest.mark.asyncio
    async def test_load_config_skips_if_mcp_not_available(self, manager):
        """When _MCP_AVAILABLE is False, load_config returns early."""
        config = {"server-a": {"command": "echo"}}

        with patch("merco.mcp.manager._MCP_AVAILABLE", False):
            with patch.object(manager, "connect", new_callable=AsyncMock) as mock_connect:
                await manager.load_config(config)

        mock_connect.assert_not_called()

    @pytest.mark.asyncio
    async def test_load_config_skips_already_connected(self, manager):
        """Skip servers already in self._servers."""
        manager._servers["server-a"] = {"config": MagicMock(), "tools": []}
        config = {"server-a": {"command": "echo"}}

        with patch("merco.mcp.manager._MCP_AVAILABLE", True):
            with patch.object(manager, "connect", new_callable=AsyncMock) as mock_connect:
                await manager.load_config(config)

        mock_connect.assert_not_called()

    @pytest.mark.asyncio
    async def test_load_config_connects_enabled(self, manager):
        """Enabled server gets connect() called."""
        config = {"server-a": {"command": "echo"}}

        with patch("merco.mcp.manager._MCP_AVAILABLE", True):
            with patch.object(manager, "connect", new_callable=AsyncMock, return_value=True) as mock_connect:
                await manager.load_config(config)

        mock_connect.assert_called_once()
        call_args = mock_connect.call_args
        assert call_args[0][0] == "server-a"

    @pytest.mark.asyncio
    async def test_load_config_stores_original_config(self, manager):
        """load_config saves original config for later reload()."""
        config = {"server-a": {"command": "echo", "enabled": False}}

        with patch("merco.mcp.manager._MCP_AVAILABLE", True):
            await manager.load_config(config)

        assert manager._original_config == config

    # --- connect tests ---

    @pytest.mark.asyncio
    async def test_connect_no_command_or_url_returns_false(self, manager):
        """connect with no command and no url returns False."""
        cfg = MCPServerConfig(name="bad", command=None, url=None)

        with patch("merco.mcp.manager._MCP_AVAILABLE", True):
            result = await manager.connect("bad", cfg)

        assert result is False

    @pytest.mark.asyncio
    async def test_connect_mcp_not_available_returns_false(self, manager):
        """When _MCP_AVAILABLE is False, connect returns False immediately."""
        cfg = MCPServerConfig(name="test", command="echo")

        with patch("merco.mcp.manager._MCP_AVAILABLE", False):
            result = await manager.connect("test", cfg)

        assert result is False

    @pytest.mark.asyncio
    async def test_connect_stdio_registers_tools(self, manager, registry):
        """Stdio connection discovers tools and registers them."""
        cfg = MCPServerConfig(name="myserver", command="echo")

        mock_tools = [
            {"name": "tool_a", "description": "First tool", "inputSchema": {}},
            {"name": "tool_b", "description": "Second tool", "inputSchema": {}},
        ]

        # Simulate a successful connection and tool discovery
        async def mock_connect_stdio(config):
            return mock_tools

        with patch("merco.mcp.manager._MCP_AVAILABLE", True):
            with patch.object(manager, "_connect_stdio", side_effect=mock_connect_stdio):
                result = await manager.connect("myserver", cfg)

        assert result is True
        assert "myserver" in manager._servers
        assert len(manager._servers["myserver"]["tools"]) == 2

        # Verify tools are registered in the registry
        assert registry.get("tool_a") is not None
        assert registry.get("tool_b") is not None
        assert registry.get("tool_a").toolset == "mcp:myserver"
        assert registry.get("tool_b").toolset == "mcp:myserver"

    @pytest.mark.asyncio
    async def test_connect_emits_observer_event(self, manager, registry, hooks):
        """Successful connect emits observer event."""
        cfg = MCPServerConfig(name="myserver", command="echo")

        mock_tools = [{"name": "tool_x", "description": "X", "inputSchema": {}}]

        async def mock_connect_stdio(config):
            return mock_tools

        with patch("merco.mcp.manager._MCP_AVAILABLE", True):
            with patch.object(manager, "_connect_stdio", side_effect=mock_connect_stdio):
                await manager.connect("myserver", cfg)

        hooks.emit.assert_called_once_with("mcp.connect", server="myserver", tools=1)

    @pytest.mark.asyncio
    async def test_connect_exception_returns_false(self, manager, registry):
        """If connection raises, connect catches it and returns False."""
        cfg = MCPServerConfig(name="fail", command="nonexistent")

        with patch("merco.mcp.manager._MCP_AVAILABLE", True):
            with patch.object(manager, "_connect_stdio", side_effect=RuntimeError("boom")):
                result = await manager.connect("fail", cfg)

        assert result is False
        assert "fail" not in manager._servers

    # --- disconnect tests ---

    @pytest.mark.asyncio
    async def test_disconnect_unregisters_tools(self, manager, registry):
        """Disconnect removes tools from registry and servers dict."""
        cfg = MCPServerConfig(name="myserver", command="echo")

        mock_tools = [
            {"name": "tool_a", "description": "First", "inputSchema": {}},
            {"name": "tool_b", "description": "Second", "inputSchema": {}},
        ]

        async def mock_connect_stdio(config):
            return mock_tools

        with patch("merco.mcp.manager._MCP_AVAILABLE", True):
            with patch.object(manager, "_connect_stdio", side_effect=mock_connect_stdio):
                await manager.connect("myserver", cfg)

        # Verify tools registered
        assert registry.get("tool_a") is not None
        assert registry.get("tool_b") is not None
        assert "myserver" in manager._servers

        # Disconnect
        await manager.disconnect("myserver")

        # Verify tools unregistered
        assert registry.get("tool_a") is None
        assert registry.get("tool_b") is None
        assert "myserver" not in manager._servers

    @pytest.mark.asyncio
    async def test_disconnect_idempotent(self, manager):
        """Disconnect on unknown server doesn't raise."""
        await manager.disconnect("nonexistent")

    # --- status tests ---

    def test_status_returns_connected_info(self, manager, registry):
        """status() returns dict with connected servers info."""
        # Simulate a connected server
        tool_a = MCPServerTool(
            {"name": "tool_a", "description": "A", "inputSchema": {}}, server_name="srv", handler=None
        )
        tool_b = MCPServerTool(
            {"name": "tool_b", "description": "B", "inputSchema": {}}, server_name="srv", handler=None
        )
        cfg = MCPServerConfig(name="srv", command="echo", enabled=True)
        manager._servers["srv"] = {"config": cfg, "tools": [tool_a, tool_b]}

        status = manager.status()

        assert "srv" in status
        assert status["srv"]["connected"] is True
        assert status["srv"]["tools_count"] == 2
        assert status["srv"]["enabled"] is True

    def test_status_empty(self, manager):
        """status() returns empty dict when no servers connected."""
        assert manager.status() == {}

    # --- reload tests ---

    @pytest.mark.asyncio
    async def test_reload_disconnects_and_reconnects(self, manager, registry):
        """reload() disconnects all and re-loads config."""
        cfg = MCPServerConfig(name="srv", command="echo")

        mock_tools = [{"name": "tool_x", "description": "X", "inputSchema": {}}]

        async def mock_connect_stdio(config):
            return mock_tools

        with patch("merco.mcp.manager._MCP_AVAILABLE", True):
            with patch.object(manager, "_connect_stdio", side_effect=mock_connect_stdio):
                await manager.connect("srv", cfg)

        assert "srv" in manager._servers

        # Now reload with a different config
        manager._original_config = {"srv2": {"command": "ls"}}

        mock_tools2 = [{"name": "tool_y", "description": "Y", "inputSchema": {}}]

        async def mock_connect_stdio2(config):
            return mock_tools2

        with patch("merco.mcp.manager._MCP_AVAILABLE", True):
            with patch.object(manager, "_connect_stdio", side_effect=mock_connect_stdio2):
                await manager.reload()

        assert "srv" not in manager._servers
        assert "srv2" in manager._servers
        assert len(manager._servers["srv2"]["tools"]) == 1
        assert manager._servers["srv2"]["tools"][0].name == "tool_y"

    # --- _call_tool tests ---

    @pytest.mark.asyncio
    async def test_call_tool_not_found(self, manager):
        """_call_tool returns error when tool name not found."""
        result = await manager._call_tool("nonexistent", {})
        assert result["isError"] is True
        assert "not found" in result["error"]

    @pytest.mark.asyncio
    async def test_call_tool_finds_and_delegates(self, manager):
        """_call_tool finds the tool and delegates to _call_stdio_tool."""
        cfg = MCPServerConfig(name="srv", command="echo")
        tool = MCPServerTool({"name": "tool_x", "inputSchema": {}}, server_name="srv", handler=None)
        manager._servers["srv"] = {"config": cfg, "tools": [tool]}

        with patch.object(
            manager, "_call_stdio_tool", new_callable=AsyncMock, return_value={"result": "ok"}
        ) as mock_call:
            result = await manager._call_tool("tool_x", {"arg": 1})

        assert result == {"result": "ok"}
        mock_call.assert_called_once_with(cfg, "tool_x", {"arg": 1})

    @pytest.mark.asyncio
    async def test_call_tool_http_delegates(self, manager):
        """_call_tool delegates to _call_http_tool for URL-based configs."""
        cfg = MCPServerConfig(name="srv", url="http://localhost/mcp")
        tool = MCPServerTool({"name": "tool_h", "inputSchema": {}}, server_name="srv", handler=None)
        manager._servers["srv"] = {"config": cfg, "tools": [tool]}

        with patch.object(
            manager, "_call_http_tool", new_callable=AsyncMock, return_value={"data": "http_result"}
        ) as mock_call:
            result = await manager._call_tool("tool_h", {})

        assert result == {"data": "http_result"}
        mock_call.assert_called_once_with(cfg, "tool_h", {})

    # --- _unregister_tools tests ---

    @pytest.mark.asyncio
    async def test_unregister_tools_clears_registry(self, manager, registry):
        """_unregister_tools removes all tools from registry for a server."""
        tool_a = MCPServerTool({"name": "a", "inputSchema": {}}, server_name="srv", handler=None)
        tool_b = MCPServerTool({"name": "b", "inputSchema": {}}, server_name="srv", handler=None)
        registry.register(tool_a)
        registry.register(tool_b)
        manager._servers["srv"] = {"config": MagicMock(), "tools": [tool_a, tool_b]}

        assert registry.get("a") is not None
        assert registry.get("b") is not None

        await manager._unregister_tools("srv")

        assert registry.get("a") is None
        assert registry.get("b") is None


class TestMCPImportHandling:
    """Tests for _MCP_AVAILABLE flag behavior."""

    def test_import_missing_handled(self):
        """Verify _MCP_AVAILABLE exists as a module-level boolean."""
        from merco.mcp import manager as mcp_manager

        assert hasattr(mcp_manager, "_MCP_AVAILABLE")
        assert isinstance(mcp_manager._MCP_AVAILABLE, bool)

    def test_manager_instantiable_without_mcp(self):
        """MCPServerManager can be instantiated even when mcp is not installed."""
        registry = ToolRegistry()
        mgr = MCPServerManager(tool_registry=registry)
        assert mgr._registry is registry
        assert mgr._servers == {}

    @pytest.mark.asyncio
    async def test_load_config_handles_missing_mcp_gracefully(self):
        """load_config doesn't crash when mcp is not installed."""
        registry = ToolRegistry()
        mgr = MCPServerManager(tool_registry=registry)
        config = {"server-a": {"command": "echo"}}

        # Force _MCP_AVAILABLE to False
        with patch("merco.mcp.manager._MCP_AVAILABLE", False):
            await mgr.load_config(config)

        assert mgr._original_config == config
        assert mgr._servers == {}
