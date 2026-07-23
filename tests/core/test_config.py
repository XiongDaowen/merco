"""ModelConfig + StreamingConfig cleanup."""
import json, tempfile, os
from merco.core.config import ModelConfig, StreamingConfig, MercoConfig


def test_model_config_no_resolve_no_stream_options():
    cfg = ModelConfig(provider="openai", model="gpt-4o")
    assert not hasattr(cfg, "resolve")           # deleted
    assert not hasattr(cfg, "stream_options")    # deleted
    assert cfg.request_cooldown == 0.3           # new, absorbs hardcoded cooldown
    assert cfg.fallbacks == []                    # new


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
        assert cfg.streaming.think is False      # migrated from stream_thinking
    finally:
        os.unlink(path)


def test_load_no_longer_calls_resolve(monkeypatch):
    # resolve() is gone; load() must not reference it. Just ensure load works.
    monkeypatch.setattr(MercoConfig, "_find_config", lambda: None)
    cfg = MercoConfig.load(None)
    assert cfg.model.provider == "openai"
