"""配置模块测试"""

from merco.core.config import MercoConfig
from merco.mcp.config import MCPServerConfig


class TestConfig:
    def test_default_config(self):
        cfg = MercoConfig()
        assert cfg.username == "user"
        assert cfg.model.provider == "openai"
        assert cfg.model.model == "gpt-4"

    def test_config_to_dict(self):
        cfg = MercoConfig()
        data = cfg._to_dict()
        assert "username" in data
        assert "model" in data
        # memory_enabled and memory_path are now nested under "memory"
        assert "memory_enabled" not in data
        assert "memory_path" not in data

    def test_config_from_dict(self):
        data = {
            "username": "test_user",
            "model": {"provider": "anthropic", "model": "claude-3"},
        }
        cfg = MercoConfig._from_dict(data)
        assert cfg.username == "test_user"
        assert cfg.model.provider == "anthropic"

    def test_memory_nested_to_dict(self):
        """memory_enabled and memory_path are nested under 'memory' key."""
        cfg = MercoConfig()
        cfg.memory_enabled = False
        cfg.memory_path = "/custom/memory"
        data = cfg._to_dict()
        assert "memory" in data
        assert data["memory"]["enabled"] is False
        assert data["memory"]["path"] == "/custom/memory"

    def test_memory_nested_from_dict(self):
        """memory_enabled and memory_path are read from nested 'memory' dict."""
        data = {
            "memory": {
                "enabled": False,
                "path": "/custom/memory",
            }
        }
        cfg = MercoConfig._from_dict(data)
        assert cfg.memory_enabled is False
        assert cfg.memory_path == "/custom/memory"

    def test_memory_recall_defaults(self):
        cfg = MercoConfig()
        assert cfg.memory_recall_enabled is True
        assert cfg.memory_recall_limit == 3
        assert cfg.memory_recall_max_chars == 300
        assert cfg.memory_recall_threshold == 0.0

    def test_memory_recall_to_dict(self):
        cfg = MercoConfig()
        data = cfg._to_dict()
        assert "memory" in data
        assert data["memory"]["recall_enabled"] is True
        assert data["memory"]["recall_limit"] == 3
        assert data["memory"]["recall_max_chars"] == 300
        assert data["memory"]["recall_threshold"] == 0.0

    def test_memory_recall_from_dict(self):
        data = {
            "memory": {
                "recall_enabled": False,
                "recall_limit": 5,
                "recall_max_chars": 500,
                "recall_threshold": 0.8,
            }
        }
        cfg = MercoConfig._from_dict(data)
        assert cfg.memory_recall_enabled is False
        assert cfg.memory_recall_limit == 5
        assert cfg.memory_recall_max_chars == 500
        assert cfg.memory_recall_threshold == 0.8

    def test_memory_recall_from_dict_with_defaults(self):
        data = {}
        cfg = MercoConfig._from_dict(data)
        assert cfg.memory_recall_enabled is True
        assert cfg.memory_recall_limit == 3
        assert cfg.memory_recall_max_chars == 300
        assert cfg.memory_recall_threshold == 0.0

    def test_memory_auto_extract_defaults(self):
        cfg = MercoConfig()
        assert cfg.memory_auto_extract_on_session_end is False
        assert cfg.memory_extract_max_per_session == 3
        assert cfg.memory_extract_min_messages == 5

    def test_memory_auto_extract_to_dict(self):
        cfg = MercoConfig()
        data = cfg._to_dict()
        assert data["memory"]["auto_extract_on_session_end"] is False
        assert data["memory"]["extract_max_per_session"] == 3
        assert data["memory"]["extract_min_messages"] == 5

    def test_memory_auto_extract_from_dict(self):
        data = {
            "memory": {
                "auto_extract_on_session_end": True,
                "extract_max_per_session": 7,
                "extract_min_messages": 2,
            }
        }
        cfg = MercoConfig._from_dict(data)
        assert cfg.memory_auto_extract_on_session_end is True
        assert cfg.memory_extract_max_per_session == 7
        assert cfg.memory_extract_min_messages == 2

    def test_partial_memory_dict(self):
        """Only some memory keys provided — rest use defaults."""
        data = {
            "memory": {
                "enabled": False,
                "recall_limit": 10,
            }
        }
        cfg = MercoConfig._from_dict(data)
        assert cfg.memory_enabled is False
        assert cfg.memory_path == "~/.merco/memory"  # default
        assert cfg.memory_recall_enabled is True       # default
        assert cfg.memory_recall_limit == 10
        assert cfg.memory_recall_max_chars == 300      # default
        assert cfg.memory_recall_threshold == 0.0      # default

    def test_memory_value_is_string(self):
        """Non-dict 'memory' value should not crash — treated as empty dict."""
        data = {"memory": "off"}
        cfg = MercoConfig._from_dict(data)
        assert cfg.memory_enabled is True   # default
        assert cfg.memory_path == "~/.merco/memory"

    def test_memory_value_is_null(self):
        """Non-dict 'memory' value (None/null) should not crash."""
        data = {"memory": None}
        cfg = MercoConfig._from_dict(data)
        assert cfg.memory_enabled is True   # default
        assert cfg.memory_path == "~/.merco/memory"

    def test_model_value_is_string(self):
        """Non-dict 'model' value should not crash — treated as empty dict."""
        data = {"model": "off"}
        cfg = MercoConfig._from_dict(data)
        assert cfg.model.provider == "openai"  # default
        assert cfg.model.model == "gpt-4"      # default

    def test_model_value_is_null(self):
        """Non-dict 'model' value (None/null) should not crash."""
        data = {"model": None}
        cfg = MercoConfig._from_dict(data)
        assert cfg.model.provider == "openai"  # default
        assert cfg.model.model == "gpt-4"      # default

    def test_memory_flat_backward_compat(self):
        """Old flat memory_enabled/memory_path still works as fallback."""
        data = {
            "memory_enabled": False,
            "memory_path": "/old/style/path",
        }
        cfg = MercoConfig._from_dict(data)
        assert cfg.memory_enabled is False
        assert cfg.memory_path == "/old/style/path"

    def test_memory_nested_overrides_flat(self):
        """Nested 'memory' keys take priority over legacy flat keys."""
        data = {
            "memory_enabled": False,
            "memory_path": "/old/path",
            "memory": {
                "enabled": True,
                "path": "/new/path",
            }
        }
        cfg = MercoConfig._from_dict(data)
        assert cfg.memory_enabled is True
        assert cfg.memory_path == "/new/path"

    # ── Session fork config tests ──

    def test_session_fork_defaults(self):
        """fork_enabled and fork_auto_on_compress default to True."""
        cfg = MercoConfig()
        assert cfg.fork_enabled is True
        assert cfg.fork_auto_on_compress is True

    def test_session_fork_to_dict(self):
        """_to_dict includes 'session' key with fork fields."""
        cfg = MercoConfig()
        cfg.fork_enabled = False
        cfg.fork_auto_on_compress = False
        data = cfg._to_dict()
        assert "session" in data
        assert data["session"]["fork_enabled"] is False
        assert data["session"]["fork_auto_on_compress"] is False

    def test_session_fork_from_dict(self):
        """_from_dict reads fork settings from 'session' block."""
        data = {
            "session": {
                "fork_enabled": False,
                "fork_auto_on_compress": False,
            }
        }
        cfg = MercoConfig._from_dict(data)
        assert cfg.fork_enabled is False
        assert cfg.fork_auto_on_compress is False

    # ── fork_reset_observer config tests ──

    def test_fork_reset_observer_default(self):
        """fork_reset_observer defaults to False."""
        cfg = MercoConfig()
        assert cfg.fork_reset_observer is False

    def test_fork_reset_observer_set_true_via_dict(self):
        """_from_dict reads fork_reset_observer from 'session' block."""
        data = {
            "session": {
                "fork_reset_observer": True,
            }
        }
        cfg = MercoConfig._from_dict(data)
        assert cfg.fork_reset_observer is True

    def test_fork_reset_observer_in_to_dict(self):
        """_to_dict includes fork_reset_observer in 'session' block."""
        cfg = MercoConfig()
        cfg.fork_reset_observer = True
        data = cfg._to_dict()
        assert "session" in data
        assert data["session"]["fork_reset_observer"] is True

    # ── MCP servers config tests ──

    def test_mcp_servers_default(self):
        """mcp_servers defaults to an empty dict."""
        cfg = MercoConfig()
        assert cfg.mcp_servers == {}

    def test_mcp_servers_from_dict(self):
        """mcp_servers dict is preserved on round-trip through _from_dict / _to_dict."""
        data = {
            "mcp_servers": {
                "filesystem": {
                    "command": "npx",
                    "args": ["-y", "@modelcontextprotocol/server-filesystem"],
                    "enabled": True,
                },
                "github": {
                    "url": "https://api.github.com/mcp",
                    "headers": {"Authorization": "Bearer xxx"},
                },
            }
        }
        cfg = MercoConfig._from_dict(data)
        assert "filesystem" in cfg.mcp_servers
        assert "github" in cfg.mcp_servers
        assert cfg.mcp_servers["filesystem"]["command"] == "npx"
        assert cfg.mcp_servers["github"]["url"] == "https://api.github.com/mcp"

        # round-trip
        out = cfg._to_dict()
        assert out["mcp_servers"] == data["mcp_servers"]

    def test_mcp_server_config_from_dict(self):
        """MCPServerConfig.from_dict() works with command transport."""
        data = {
            "command": "python",
            "args": ["-m", "my_mcp_server"],
            "timeout": 60,
            "sandbox": "allow",
        }
        cfg = MCPServerConfig.from_dict("my_server", data)
        assert cfg.name == "my_server"
        assert cfg.command == "python"
        assert cfg.args == ["-m", "my_mcp_server"]
        assert cfg.url is None
        assert cfg.timeout == 60
        assert cfg.sandbox == "allow"
        assert cfg.enabled is True  # default

    def test_mcp_server_config_url(self):
        """MCPServerConfig.from_dict() works with url transport."""
        data = {
            "url": "http://localhost:8080/mcp",
            "headers": {"X-API-Key": "secret"},
            "connect_timeout": 5,
        }
        cfg = MCPServerConfig.from_dict("remote_server", data)
        assert cfg.name == "remote_server"
        assert cfg.url == "http://localhost:8080/mcp"
        assert cfg.command is None
        assert cfg.headers == {"X-API-Key": "secret"}
        assert cfg.connect_timeout == 5
        assert cfg.env == {}  # default

    # ── plugins_paths config tests ──

    def test_plugins_paths_default(self):
        """plugins_paths 默认对齐 skills_paths 约定"""
        cfg = MercoConfig()
        assert cfg.plugins_paths == ["./.merco/plugins", "~/.config/merco/plugins"]

    def test_plugins_paths_from_dict(self):
        """从 dict 加载 plugins_paths"""
        cfg = MercoConfig._from_dict({"plugins_paths": ["/custom/plugins"]})
        assert cfg.plugins_paths == ["/custom/plugins"]
