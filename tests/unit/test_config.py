"""配置模块测试"""

import pytest
from openmercury.core.config import OpenMercuryConfig, ModelConfig


class TestConfig:
    def test_default_config(self):
        cfg = OpenMercuryConfig()
        assert cfg.username == "user"
        assert cfg.model.provider == "openai"
        assert cfg.model.model == "gpt-4"

    def test_config_to_dict(self):
        cfg = OpenMercuryConfig()
        data = cfg._to_dict()
        assert "username" in data
        assert "model" in data

    def test_config_from_dict(self):
        data = {
            "username": "test_user",
            "model": {"provider": "anthropic", "model": "claude-3"},
        }
        cfg = OpenMercuryConfig._from_dict(data)
        assert cfg.username == "test_user"
        assert cfg.model.provider == "anthropic"
