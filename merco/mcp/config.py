"""MCP server configuration dataclass."""
from dataclasses import dataclass, field


@dataclass
class MCPServerConfig:
    name: str
    command: str | None = None
    args: list[str] = field(default_factory=list)
    url: str | None = None
    headers: dict = field(default_factory=dict)
    env: dict = field(default_factory=dict)
    enabled: bool = True
    timeout: int = 30
    connect_timeout: int = 10
    sandbox: str = "ask"
    sandbox_rules: list = field(default_factory=list)

    @classmethod
    def from_dict(cls, name: str, data: dict) -> "MCPServerConfig":
        if not isinstance(data, dict):
            data = {}
        return cls(
            name=name,
            command=data.get("command"),
            args=data.get("args", []),
            url=data.get("url"),
            headers=data.get("headers", {}),
            env=data.get("env", {}),
            enabled=data.get("enabled", True),
            timeout=data.get("timeout", 30),
            connect_timeout=data.get("connect_timeout", 10),
            sandbox=data.get("sandbox", "ask"),
            sandbox_rules=data.get("sandbox_rules", []),
        )
