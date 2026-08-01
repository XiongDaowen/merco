"""ModelConfig + StreamingConfig cleanup."""

import json
import os
import tempfile

from merco.core.config import MercoConfig, ModelConfig, StreamingConfig


def test_model_config_defaults():
    cfg = ModelConfig(provider="openai", model="gpt-4o")
    assert not hasattr(cfg, "resolve")  # resolve() removed
    assert cfg.request_cooldown == 0.3  # absorbs hardcoded cooldown
    assert cfg.fallbacks == []


def test_streaming_config_grouped():
    cfg = MercoConfig()
    assert isinstance(cfg.streaming, StreamingConfig)
    assert cfg.streaming.enabled is False
    assert cfg.streaming.think is True
    assert cfg.streaming.render_interval == 0.05


def test_streaming_bool_migration_from_old_config():
    """One-time migration: old `streaming: true` -> `streaming: {enabled: true}`."""
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump({"streaming": True, "stream_thinking": False}, f)
        path = f.name
    try:
        cfg = MercoConfig.load(path)
        assert cfg.streaming.enabled is True
        assert cfg.streaming.think is False  # migrated from stream_thinking
    finally:
        os.unlink(path)


def test_load_no_longer_calls_resolve(monkeypatch):
    # resolve() is gone; load() must not reference it. Just ensure load works.
    monkeypatch.setattr(MercoConfig, "_find_config", lambda: None)
    cfg = MercoConfig.load(None)
    assert cfg.model.provider == "openai"


class TestSessionSummarizeConfig:
    def test_defaults(self):
        from merco.core.config import MercoConfig

        cfg = MercoConfig()
        assert cfg.session_summarize is True
        assert cfg.session_summarize_min_messages == 8

    def test_roundtrip(self, tmp_path):
        from merco.core.config import MercoConfig

        cfg = MercoConfig()
        cfg.session_summarize = False
        cfg.session_summarize_min_messages = 12
        path = str(tmp_path / "cfg.json")
        cfg.save(path)

        loaded = MercoConfig.load(path)
        assert loaded.session_summarize is False
        assert loaded.session_summarize_min_messages == 12


class TestAutoContextWindowConfig:
    def test_defaults(self):
        from merco.core.config import MercoConfig

        cfg = MercoConfig()
        assert cfg.auto_context_window is True

    def test_roundtrip(self, tmp_path):
        from merco.core.config import MercoConfig

        cfg = MercoConfig()
        cfg.auto_context_window = False
        path = str(tmp_path / "cfg.json")
        cfg.save(path)

        loaded = MercoConfig.load(path)
        assert loaded.auto_context_window is False
