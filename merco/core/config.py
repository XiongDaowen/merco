"""配置系统 - 支持多层级配置合并 + provider 自动发现"""

import os
import json
import logging
from pathlib import Path
from dataclasses import dataclass, field

logger = logging.getLogger("merco.config")

# ── Provider 注册表：内置平台的完整元数据 ──
# 新增平台只需加一条 ProviderInfo，setup 向导自动适配。


@dataclass
class ProviderInfo:
    """平台元数据 — 一条记录即可驱动配置向导和自动补全"""
    key: str              # provider id: "openai", "minimax", ...
    name: str             # 显示名: "OpenAI", "MiniMax"
    base_url: str         # 默认 API 端点
    key_env: str          # 环境变量名
    default_model: str    # 推荐模型
    models: list[str]     # 已知模型列表（空 = 用户自行输入）
    key_help: str         # 获取 API key 的链接
    description: str      # 一句话介绍

    # 向后兼容：支持 dict-style 访问（旧代码用 PROVIDER_REGISTRY["openai"]["base_url"]）
    def __getitem__(self, key: str):
        if key == "base_url":
            return self.base_url
        if key == "key_env":
            return self.key_env
        raise KeyError(key)


PROVIDER_REGISTRY: dict[str, ProviderInfo] = {
    "openai": ProviderInfo(
        key="openai",
        name="OpenAI",
        base_url="https://api.openai.com/v1",
        key_env="OPENAI_API_KEY",
        default_model="gpt-4o",
        models=["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "o3-mini", "o1"],
        key_help="https://platform.openai.com/api-keys",
        description="最通用的平台，GPT-4o / o3 系列",
    ),
    "minimax": ProviderInfo(
        key="minimax",
        name="MiniMax",
        base_url="https://api.minimaxi.com/v1",
        key_env="MINIMAX_API_KEY",
        default_model="MiniMax-M2.7",
        models=["MiniMax-M2.7", "MiniMax-Text-01", "abab7-chat"],
        key_help="https://platform.minimaxi.com/user-center/basic-information",
        description="国产平台，MiniMax-M2.7 性价比高",
    ),
    "anthropic": ProviderInfo(
        key="anthropic",
        name="Anthropic",
        base_url="https://api.anthropic.com",
        key_env="ANTHROPIC_API_KEY",
        default_model="claude-sonnet-4-20250514",
        models=["claude-sonnet-4-20250514", "claude-3-5-haiku-20241022",
                "claude-3-opus-20240229", "claude-3-5-sonnet-20241022"],
        key_help="https://console.anthropic.com/settings/keys",
        description="Claude 系列，代码能力优秀",
    ),
    "openrouter": ProviderInfo(
        key="openrouter",
        name="OpenRouter",
        base_url="https://openrouter.ai/api/v1",
        key_env="OPENROUTER_API_KEY",
        default_model="anthropic/claude-sonnet-4",
        models=[],  # 模型太多，用户自行输入
        key_help="https://openrouter.ai/keys",
        description="模型聚合平台，一个 key 调用上百种模型",
    ),
    "deepseek": ProviderInfo(
        key="deepseek",
        name="DeepSeek",
        base_url="https://api.deepseek.com/v1",
        key_env="DEEPSEEK_API_KEY",
        default_model="deepseek-chat",
        models=["deepseek-chat", "deepseek-reasoner"],
        key_help="https://platform.deepseek.com/api_keys",
        description="国产平台，deepseek-reasoner 推理能力强",
    ),
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
    extra_params: dict = field(default_factory=dict)
    headers: dict = field(default_factory=dict)
    stream_options: dict | None = None

    def resolve(self):
        """后处理：根据 provider 名补齐未填的字段"""
        entry = PROVIDER_REGISTRY.get(self.provider)
        if entry:
            if not self.base_url:
                self.base_url = entry.base_url
            if not self.api_key:
                self.api_key = os.environ.get(entry.key_env, "")
        elif not self.base_url:
            # 未收录的 provider —— 用户必须显式写 base_url
            logger.warning(
                "Provider '%s' 未在注册表中。请确认 base_url 已正确填写，"
                "或使用 provider: 'custom' 明确标注。", self.provider
            )


@dataclass
class MercoConfig:
    """主配置类"""
    username: str = "user"
    model: ModelConfig = field(default_factory=ModelConfig)
    max_tool_calls: int = 50
    max_input_tokens: int = 64000
    compression_threshold: float = 0.75
    skills_paths: list = field(default_factory=lambda: ["./.merco/skills", "~/.config/merco/skills"])
    memory_enabled: bool = True
    memory_path: str = "~/.merco/memory"
    memory_backend: str = "json"
    log_level: str = "INFO"
    sandbox_mode: str = "ask"
    sandbox_rules: list = field(default_factory=list)
    streaming: bool = False
    stream_thinking: bool = True
    stream_content: bool = True
    stream_thinking_transient: bool = False  # 流式思考内容是否仅临时显示（不保留思考面板）
    stream_render_interval: float = 0.3  # 流式 reasoning 面板最小渲染间隔（秒），0=不限制
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

        # 后处理：根据 provider 补全未填字段
        cfg.model.resolve()
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
                "stream_options": self.model.stream_options,
            },
            "max_tool_calls": self.max_tool_calls,
            "max_input_tokens": self.max_input_tokens,
            "compression_threshold": self.compression_threshold,
            "skills_paths": self.skills_paths,
            "log_level": self.log_level,
            "sandbox_mode": self.sandbox_mode,
            "sandbox_rules": self.sandbox_rules,
            "streaming": self.streaming,
            "stream_thinking": self.stream_thinking,
            "stream_content": self.stream_content,
            "stream_thinking_transient": self.stream_thinking_transient,
            "stream_render_interval": self.stream_render_interval,
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

    @classmethod
    def _from_dict(cls, data: dict) -> "MercoConfig":
        model_data = data.get("model", {})
        if not isinstance(model_data, dict):
            model_data = {}
        model = ModelConfig(
            provider=model_data.get("provider", "openai"),
            model=model_data.get("model", "gpt-4"),
            api_key=model_data.get("api_key"),
            base_url=model_data.get("base_url"),
            temperature=model_data.get("temperature", 0.7),
            max_tokens=model_data.get("max_tokens", 4096),
            extra_params=model_data.get("extra_params", {}),
            headers=model_data.get("headers", {}),
            stream_options=model_data.get("stream_options"),
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
            memory_enabled=memory_data.get("enabled", data.get("memory_enabled", True)),
            memory_path=memory_data.get("path", data.get("memory_path", "~/.merco/memory")),
            memory_backend=memory_data.get("backend", "json"),
            log_level=data.get("log_level", "INFO"),
            sandbox_mode=data.get("sandbox_mode", "ask"),
            sandbox_rules=data.get("sandbox_rules", []),
            streaming=data.get("streaming", False),
            stream_thinking=data.get("stream_thinking", True),
            stream_content=data.get("stream_content", True),
            stream_thinking_transient=data.get("stream_thinking_transient", False),
            stream_render_interval=data.get("stream_render_interval", 0.05),
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
