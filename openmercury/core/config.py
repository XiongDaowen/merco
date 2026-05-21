"""配置系统 - 支持多层级配置合并"""

import os
import json
from pathlib import Path
from typing import Any, Optional
from dataclasses import dataclass, field


@dataclass
class ModelConfig:
    """模型配置"""
    provider: str = "openai"
    model: str = "gpt-4"
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    temperature: float = 0.7
    max_tokens: int = 4096


@dataclass
class OpenMercuryConfig:
    """主配置类"""
    username: str = "user"
    model: ModelConfig = field(default_factory=ModelConfig)
    max_tool_calls: int = 15  # 单次对话最大工具调用次数，防死循环
    skills_paths: list = field(default_factory=lambda: ["./.openmercury/skills", "~/.config/openmercury/skills"])
    memory_enabled: bool = True
    memory_path: str = "~/.openmercury/memory"
    log_level: str = "INFO"
    sandbox_mode: str = "ask"  # allow, ask, deny

    @classmethod
    def load(cls, config_path: Optional[str] = None) -> "OpenMercuryConfig":
        """从文件加载配置"""
        if config_path is None:
            config_path = cls._find_config()

        if config_path and Path(config_path).exists():
            with open(config_path) as f:
                data = json.load(f)
            return cls._from_dict(data)

        return cls()

    def save(self, config_path: str):
        """保存配置到文件"""
        with open(config_path, "w") as f:
            json.dump(self._to_dict(), f, indent=2)

    def merge(self, other: "OpenMercuryConfig"):
        """合并配置（other 优先级更高）"""
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
            "skills_paths": self.skills_paths,
            "memory_enabled": self.memory_enabled,
            "memory_path": self.memory_path,
            "log_level": self.log_level,
            "sandbox_mode": self.sandbox_mode,
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
            max_tool_calls=data.get("max_tool_calls", 15),
            skills_paths=data.get("skills_paths", ["./.openmercury/skills", "~/.config/openmercury/skills"]),
            memory_enabled=data.get("memory_enabled", True),
            memory_path=data.get("memory_path", "~/.openmercury/memory"),
            log_level=data.get("log_level", "INFO"),
            sandbox_mode=data.get("sandbox_mode", "ask"),
        )

    @staticmethod
    def _find_config() -> Optional[str]:
        """查找配置文件"""
        candidates = [
            "./openmercury.json",
            "./.openmercury/openmercury.json",
            os.path.expanduser("~/.config/openmercury/config.json"),
        ]
        for path in candidates:
            if Path(path).exists():
                return path
        return None
