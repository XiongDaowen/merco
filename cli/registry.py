"""命令注册表 — 可拓展、UI 无关的命令定义与查询"""

from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass
class CommandDef:
    name: str
    description: str
    handler: Callable
    sub_commands: dict[str, str] = field(default_factory=dict)
    group: str = "general"


class CommandRegistry:
    def __init__(self):
        self._commands: dict[str, CommandDef] = {}

    def register(
        self, name: str, description: str, handler=None, *, sub: dict[str, str] | None = None, group: str = "general"
    ):
        """注册命令。可做装饰器用。"""

        def decorator(fn):
            self._commands[name] = CommandDef(
                name=name,
                description=description,
                handler=fn,
                sub_commands=sub or {},
                group=group,
            )
            return fn

        if handler is not None:
            return decorator(handler)
        return decorator

    def match(self, prefix: str) -> list[CommandDef]:
        """前缀匹配。"""
        prefix = prefix.lower()
        return sorted(
            [c for c in self._commands.values() if c.name.lower().startswith(prefix)],
            key=lambda c: c.name,
        )

    def get_all(self, group: str | None = None) -> list[CommandDef]:
        """全部或按分组。"""
        cmds = list(self._commands.values())
        if group:
            cmds = [c for c in cmds if c.group == group]
        return sorted(cmds, key=lambda c: c.name)

    def get(self, name: str) -> CommandDef | None:
        return self._commands.get(name.lower())

    def get_help_text(self) -> str:
        groups: dict[str, list[str]] = {}
        for cmd in sorted(self._commands.values(), key=lambda c: c.name):
            groups.setdefault(cmd.group, []).append(f"{cmd.name:14s} - {cmd.description}")
        lines = ["[bold]可用命令[/bold]\n"]
        for grp, entries in groups.items():
            lines.append(f"[bold]{grp}[/bold]")
            lines.extend(f"  {e}" for e in entries)
            lines.append("")
        return "\n".join(lines)

    def __len__(self):
        return len(self._commands)


cmd_registry = CommandRegistry()
