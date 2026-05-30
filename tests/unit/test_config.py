"""配置模块测试"""

import pytest
from merco.core.config import MercoConfig, ModelConfig


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
