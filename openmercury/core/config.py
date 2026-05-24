"""配置系统 - 支持多层级配置合并 + provider 自动发现"""

import os
import json
import logging
from pathlib import Path
from dataclasses import dataclass, field

logger = logging.getLogger("openmercury.config")

# ── Provider 注册表：内置平台的默认配置 ──
# 用户只需写 provider: "minimax"，自动补 base_url。
# 新平台只需加一条记录即可扩展。
PROVIDER_REGISTRY = {
    "openai":     {"base_url": "https://api.openai.com/v1",       "key_env": "OPENAI_API_KEY"},
    "minimax":    {"base_url": "https://api.minimaxi.com/v1",     "key_env": "MINIMAX_API_KEY"},
    "anthropic":  {"base_url": "https://api.anthropic.com",       "key_env": "ANTHROPIC_API_KEY"},
    "openrouter": {"base_url": "https://openrouter.ai/api/v1",    "key_env": "OPENROUTER_API_KEY"},
    "deepseek":   {"base_url": "https://api.deepseek.com/v1",     "key_env": "DEEPSEEK_API_KEY"},
}


@dataclass
class ModelConfig:
    """模型配置"""
    provider: str = "openai"
    model: str = "gpt-4"
    api_key: str | None = None
    base_url: str | None = None
    temperature: float = 0.7
    max_tokens: int = 4096

    def resolve(self):
        """后处理：根据 provider 名补齐未填的字段"""
        entry = PROVIDER_REGISTRY.get(self.provider)
        if entry:
            if not self.base_url:
                self.base_url = entry["base_url"]
            if not self.api_key:
                self.api_key = os.environ.get(entry["key_env"], "")
        elif not self.base_url:
            # 未收录的 provider —— 用户必须显式写 base_url
            logger.warning(
                "Provider '%s' 未在注册表中。请确认 base_url 已正确填写，"
                "或使用 provider: 'custom' 明确标注。", self.provider
            )


@dataclass
class OpenMercuryConfig:
    """主配置类"""
    username: str = "user"
    model: ModelConfig = field(default_factory=ModelConfig)
    max_tool_calls: int = 50
    max_input_tokens: int = 64000
    compression_threshold: float = 0.75
    skills_paths: list = field(default_factory=lambda: ["./.openmercury/skills", "~/.config/openmercury/skills"])
    memory_enabled: bool = True
    memory_path: str = "~/.openmercury/memory"
    log_level: str = "INFO"
    sandbox_mode: str = "ask"
    streaming: bool = False
    stream_thinking: bool = True
    stream_content: bool = False

    @classmethod
    def load(cls, config_path: str | None = None) -> "OpenMercuryConfig":
        if config_path is None:
            config_path = cls._find_config()

        if config_path and Path(config_path).exists():
            with open(config_path) as f:
                data = json.load(f)
            cfg = cls._from_dict(data)
        else:
            cfg = cls()

        # 后处理：根据 provider 补全未填字段
        cfg.model.resolve()
        return cfg

    def save(self, config_path: str):
        with open(config_path, "w") as f:
            json.dump(self._to_dict(), f, indent=2)

    def merge(self, other: "OpenMercuryConfig"):
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
            },
            "max_tool_calls": self.max_tool_calls,
            "max_input_tokens": self.max_input_tokens,
            "compression_threshold": self.compression_threshold,
            "skills_paths": self.skills_paths,
            "memory_enabled": self.memory_enabled,
            "memory_path": self.memory_path,
            "log_level": self.log_level,
            "sandbox_mode": self.sandbox_mode,
            "streaming": self.streaming,
            "stream_thinking": self.stream_thinking,
            "stream_content": self.stream_content,
        }

    @classmethod
    def _from_dict(cls, data: dict) -> "OpenMercuryConfig":
        model_data = data.get("model", {})
        model = ModelConfig(
            provider=model_data.get("provider", "openai"),
            model=model_data.get("model", "gpt-4"),
            api_key=model_data.get("api_key"),
            base_url=model_data.get("base_url"),
            temperature=model_data.get("temperature", 0.7),
            max_tokens=model_data.get("max_tokens", 4096),
        )
        return cls(
            username=data.get("username", "user"),
            model=model,
            max_tool_calls=data.get("max_tool_calls", 50),
            max_input_tokens=data.get("max_input_tokens", 64000),
            compression_threshold=data.get("compression_threshold", 0.75),
            skills_paths=data.get("skills_paths", ["./.openmercury/skills", "~/.config/openmercury/skills"]),
            memory_enabled=data.get("memory_enabled", True),
            memory_path=data.get("memory_path", "~/.openmercury/memory"),
            log_level=data.get("log_level", "INFO"),
            sandbox_mode=data.get("sandbox_mode", "ask"),
            streaming=data.get("streaming", False),
            stream_thinking=data.get("stream_thinking", True),
            stream_content=data.get("stream_content", False),
        )

    @staticmethod
    def _find_config() -> str | None:
        candidates = [
            "./openmercury.json",
            "./.openmercury/openmercury.json",
            os.path.expanduser("~/.config/openmercury/config.json"),
        ]
        for path in candidates:
            if Path(path).exists():
                return path
        return None
