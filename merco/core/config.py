"""配置系统 - 支持多层级配置合并"""

import os
import json
import logging
from pathlib import Path
from dataclasses import dataclass, field

logger = logging.getLogger("merco.config")


@dataclass
class ModelConfig:
    """模型配置 - 纯数据袋。凭证解析由 ModelRegistry.select() 负责。"""
    provider: str = "openai"
    model: str = "gpt-4"
    api_key: str | None = None
    base_url: str | None = None
    temperature: float = 0.7
    max_tokens: int = 4096
    extra_params: dict = field(default_factory=dict)
    headers: dict = field(default_factory=dict)
    request_cooldown: float = 0.3          # 吸收 agent.py 硬编码 cooldown=0.3
    fallbacks: list = field(default_factory=list)   # list[ModelConfig] for ModelFallbackRecovery


@dataclass
class StreamingConfig:
    """流式渲染配置（归组，替旧 5 扁平字段）。"""
    enabled: bool = False
    think: bool = True
    content: bool = True
    think_transient: bool = False
    render_interval: float = 0.05


@dataclass
class MercoConfig:
    """主配置类"""
    username: str = "user"
    model: ModelConfig = field(default_factory=ModelConfig)
    max_tool_calls: int = 50
    max_input_tokens: int = 64000
    compression_threshold: float = 0.75
    skills_paths: list = field(default_factory=lambda: ["./.merco/skills", "~/.config/merco/skills"])
    plugins_paths: list = field(default_factory=lambda: ["./.merco/plugins", "~/.config/merco/plugins"])
    memory_enabled: bool = True
    memory_path: str = "~/.merco/memory"
    memory_backend: str = "json"
    log_level: str = "INFO"
    sandbox_mode: str = "ask"
    sandbox_rules: list = field(default_factory=list)
    streaming: StreamingConfig = field(default_factory=StreamingConfig)
    diff_view: str = "unified"
    memory_recall_enabled: bool = True
    memory_recall_limit: int = 3
    memory_recall_max_chars: int = 300
    memory_recall_threshold: float = 0.0
    memory_auto_extract_on_session_end: bool = False
    memory_extract_max_per_session: int = 3
    memory_extract_min_messages: int = 5
    fork_enabled: bool = True
    fork_auto_on_compress: bool = True
    fork_reset_observer: bool = False  # default: inherit observer acc on fork
    mcp_servers: dict = field(default_factory=dict)
    plugins: dict = field(default_factory=dict)

    @classmethod
    def load(cls, config_path: str | None = None) -> "MercoConfig":
        if config_path is None:
            config_path = cls._find_config()

        if config_path and Path(config_path).exists():
            with open(config_path) as f:
                data = json.load(f)
            cfg = cls._from_dict(data)
        else:
            cfg = cls()

        return cfg

    def save(self, config_path: str):
        with open(config_path, "w") as f:
            json.dump(self._to_dict(), f, indent=2)

    def merge(self, other: "MercoConfig"):
        for key, value in vars(other).items():
            if value is not None:
                setattr(self, key, value)

    def _to_dict(self) -> dict:
        return {
            "username": self.username,
            "model": {
                "provider": self.model.provider,
                "model": self.model.model,
                "api_key": self.model.api_key,
                "base_url": self.model.base_url,
                "temperature": self.model.temperature,
                "max_tokens": self.model.max_tokens,
                "extra_params": self.model.extra_params or None,
                "headers": self.model.headers or None,
                "request_cooldown": self.model.request_cooldown,
                "fallbacks": [
                    {
                        "provider": m.provider,
                        "model": m.model,
                        "api_key": m.api_key,
                        "base_url": m.base_url,
                        "temperature": m.temperature,
                        "max_tokens": m.max_tokens,
                        "extra_params": m.extra_params or None,
                        "headers": m.headers or None,
                        "request_cooldown": m.request_cooldown,
                    }
                    for m in self.model.fallbacks
                ] if self.model.fallbacks else None,
            },
            "max_tool_calls": self.max_tool_calls,
            "max_input_tokens": self.max_input_tokens,
            "compression_threshold": self.compression_threshold,
            "skills_paths": self.skills_paths,
            "plugins_paths": self.plugins_paths,
            "log_level": self.log_level,
            "sandbox_mode": self.sandbox_mode,
            "sandbox_rules": self.sandbox_rules,
            "streaming": self._streaming_to_dict(self.streaming),
            "diff_view": self.diff_view,
            "memory": {
                "enabled": self.memory_enabled,
                "path": self.memory_path,
                "backend": self.memory_backend,
                "recall_enabled": self.memory_recall_enabled,
                "recall_limit": self.memory_recall_limit,
                "recall_max_chars": self.memory_recall_max_chars,
                "recall_threshold": self.memory_recall_threshold,
                "auto_extract_on_session_end": self.memory_auto_extract_on_session_end,
                "extract_max_per_session": self.memory_extract_max_per_session,
                "extract_min_messages": self.memory_extract_min_messages,
            },
            "session": {
                "fork_enabled": self.fork_enabled,
                "fork_auto_on_compress": self.fork_auto_on_compress,
                "fork_reset_observer": self.fork_reset_observer,
            },
            "mcp_servers": self.mcp_servers,
            "plugins": self.plugins,
        }

    @staticmethod
    def _streaming_to_dict(streaming: StreamingConfig) -> dict:
        return {
            "enabled": streaming.enabled,
            "think": streaming.think,
            "content": streaming.content,
            "think_transient": streaming.think_transient,
            "render_interval": streaming.render_interval,
        }

    @classmethod
    def _from_dict(cls, data: dict) -> "MercoConfig":
        model_data = data.get("model", {})
        if not isinstance(model_data, dict):
            model_data = {}
        fallbacks_raw = model_data.get("fallbacks", [])
        fallbacks = [
            ModelConfig(
                provider=f.get("provider", "openai"),
                model=f.get("model", "gpt-4"),
                api_key=f.get("api_key"),
                base_url=f.get("base_url"),
                temperature=f.get("temperature", 0.7),
                max_tokens=f.get("max_tokens", 4096),
                extra_params=f.get("extra_params", {}),
                headers=f.get("headers", {}),
                request_cooldown=f.get("request_cooldown", 0.3),
            )
            for f in fallbacks_raw
        ] if isinstance(fallbacks_raw, list) and fallbacks_raw else []
        model = ModelConfig(
            provider=model_data.get("provider", "openai"),
            model=model_data.get("model", "gpt-4"),
            api_key=model_data.get("api_key"),
            base_url=model_data.get("base_url"),
            temperature=model_data.get("temperature", 0.7),
            max_tokens=model_data.get("max_tokens", 4096),
            extra_params=model_data.get("extra_params", {}),
            headers=model_data.get("headers", {}),
            request_cooldown=model_data.get("request_cooldown", 0.3),
            fallbacks=fallbacks,
        )
        memory_data = data.get("memory", {})
        if not isinstance(memory_data, dict):
            memory_data = {}
        sess = data.get("session", {})
        if not isinstance(sess, dict):
            sess = {}
        return cls(
            username=data.get("username", "user"),
            model=model,
            max_tool_calls=data.get("max_tool_calls", 50),
            max_input_tokens=data.get("max_input_tokens", 64000),
            compression_threshold=data.get("compression_threshold", 0.75),
            skills_paths=data.get("skills_paths", ["./.merco/skills", "~/.config/merco/skills"]),
            plugins_paths=data.get("plugins_paths", ["./.merco/plugins", "~/.config/merco/plugins"]),
            memory_enabled=memory_data.get("enabled", data.get("memory_enabled", True)),
            memory_path=memory_data.get("path", data.get("memory_path", "~/.merco/memory")),
            memory_backend=memory_data.get("backend", "json"),
            log_level=data.get("log_level", "INFO"),
            sandbox_mode=data.get("sandbox_mode", "ask"),
            sandbox_rules=data.get("sandbox_rules", []),
            streaming=cls._streaming_from_dict(data),
            diff_view=data.get("diff_view", "unified"),
            memory_recall_enabled=memory_data.get("recall_enabled", True),
            memory_recall_limit=memory_data.get("recall_limit", 3),
            memory_recall_max_chars=memory_data.get("recall_max_chars", 300),
            memory_recall_threshold=memory_data.get("recall_threshold", 0.0),
            memory_auto_extract_on_session_end=memory_data.get("auto_extract_on_session_end", False),
            memory_extract_max_per_session=memory_data.get("extract_max_per_session", 3),
            memory_extract_min_messages=memory_data.get("extract_min_messages", 5),
            fork_enabled=sess.get("fork_enabled", True),
            fork_auto_on_compress=sess.get("fork_auto_on_compress", True),
            fork_reset_observer=isinstance(sess, dict) and sess.get("fork_reset_observer", False),
            mcp_servers=data.get("mcp_servers", {}),
            plugins=data.get("plugins", {}),
        )

    @staticmethod
    def _streaming_from_dict(data: dict) -> StreamingConfig:
        raw = data.get("streaming")
        if isinstance(raw, bool):        # one-time migration: old `streaming: true`
            return StreamingConfig(
                enabled=raw,
                think=data.get("stream_thinking", True),
                content=data.get("stream_content", True),
                think_transient=data.get("stream_thinking_transient", False),
                render_interval=data.get("stream_render_interval", 0.05),
            )
        if not isinstance(raw, dict):
            return StreamingConfig()
        return StreamingConfig(
            enabled=raw.get("enabled", False),
            think=raw.get("think", raw.get("stream_thinking", True)),
            content=raw.get("content", raw.get("stream_content", True)),
            think_transient=raw.get("think_transient", raw.get("stream_thinking_transient", False)),
            render_interval=raw.get("render_interval", raw.get("stream_render_interval", 0.05)),
        )

    @staticmethod
    def _find_config() -> str | None:
        candidates = [
            "./merco.json",
            "./.merco/merco.json",
            os.path.expanduser("~/.config/merco/config.json"),
        ]
        for path in candidates:
            if Path(path).exists():
                return path
        return None
