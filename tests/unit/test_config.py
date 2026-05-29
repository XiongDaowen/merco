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

    def test_config_from_dict(self):
        data = {
            "username": "test_user",
            "model": {"provider": "anthropic", "model": "claude-3"},
        }
        cfg = MercoConfig._from_dict(data)
        assert cfg.username == "test_user"
        assert cfg.model.provider == "anthropic"

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
