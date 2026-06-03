"""工具执行守卫 — 细粒度敏感命令规则链

每条规则 = tool + pattern + action，依次匹配，首个命中生效::

    guard = ToolGuard()
    guard.rule("bash", "DROP TABLE", "deny")  # 用户可加硬拦截
    # 默认规则全部 ask，确认后放行

配置 (merco.json)::

    "sandbox_rules": [
        {"tool": "bash", "pattern": "DROP TABLE", "action": "deny"},
    ]
"""

import asyncio
import logging
from dataclasses import dataclass
from rich.console import Console
from rich.panel import Panel

from .security import SecurityChecker

console = Console()
logger = logging.getLogger("merco.guard")


# ── 规则 ──────────────────────────────────────────────────

@dataclass
class GuardRule:
    tool: str     # "bash" | "write_file" | "*" 所有工具
    pattern: str
    action: str   # "ask" | "deny" | "allow"

    def to_dict(self) -> dict:
        return {"tool": self.tool, "pattern": self.pattern, "action": self.action}

    @classmethod
    def from_dict(cls, d: dict) -> "GuardRule":
        return cls(
            tool=d.get("tool", "bash"),
            pattern=d["pattern"],
            action=d.get("action", "ask"),
        )


# ── 默认规则（全部 ask，不硬拦截）─────────────────────────

_DEFAULT_RULES: list[GuardRule] = [
    GuardRule("bash", "rm -rf /", "ask"),
    GuardRule("bash", "mkfs", "ask"),
    GuardRule("bash", "dd if=", "ask"),
    GuardRule("bash", "> /dev/sd", "ask"),
    GuardRule("bash", "curl | bash", "ask"),
    GuardRule("bash", "curl | sh", "ask"),
    GuardRule("bash", "wget | bash", "ask"),
    GuardRule("bash", "wget | sh", "ask"),
    GuardRule("bash", "chmod 777 /", "ask"),
    GuardRule("bash", "rm ", "ask"),
    GuardRule("bash", "sudo ", "ask"),
    GuardRule("bash", "chmod ", "ask"),
    GuardRule("bash", "chown ", "ask"),
    GuardRule("bash", "kill ", "ask"),
    GuardRule("bash", "pkill ", "ask"),
    GuardRule("bash", "git push", "ask"),
    GuardRule("bash", "git reset --hard", "ask"),
    GuardRule("bash", "docker rm", "ask"),
    GuardRule("bash", "docker rmi", "ask"),
    GuardRule("bash", "pip install", "ask"),
    GuardRule("bash", "pip uninstall", "ask"),
    GuardRule("bash", "npm install -g", "ask"),
    GuardRule("bash", "npm uninstall -g", "ask"),
    GuardRule("bash", "apt ", "ask"),
    GuardRule("bash", "yum ", "ask"),
    GuardRule("bash", "brew ", "ask"),
    GuardRule("bash", "shutdown", "ask"),
    GuardRule("bash", "reboot", "ask"),
]


# ── ToolGuard ─────────────────────────────────────────────

class ToolGuard:
    """工具执行守卫 — 规则链。

    用法::

        guard = ToolGuard()
        guard.rule("bash", "DROP TABLE", "deny")

        if not await guard.check("bash", {"command": "rm file.txt"}):
            return  # 已拦截/取消
    """

    def __init__(self, mode: str = "ask", user_rules: list[dict] | None = None):
        self.mode = mode
        self._rules: list[GuardRule] = []

        if user_rules:
            for r in user_rules:
                self._rules.append(
                    GuardRule.from_dict(r) if isinstance(r, dict) else r
                )

        self._rules.extend(_DEFAULT_RULES)

    # ── 链式 API ──

    def rule(self, tool: str, pattern: str, action: str) -> "ToolGuard":
        """添加规则，插入链首（优先级最高）。"""
        self._rules.insert(0, GuardRule(tool, pattern, action))
        return self

    # ── 检查 ──

    async def check(self, tool_name: str, arguments: dict) -> bool:
        """检查工具是否可以执行。返回 True=放行。"""
        if self.mode == "auto":
            return True

        command = arguments.get("command", "")
        path = arguments.get("path", "")

        # 文件工具：SecurityChecker 路径检测（硬拦截）
        if path and tool_name != "bash":
            ok, reason = SecurityChecker.check_file_path(path)
            if not ok:
                self._render_path_deny(path, reason)
                return False

        return await self._check(tool_name, command)

    async def _check(self, tool: str, command: str) -> bool:
        # ── SecurityChecker 正则兜底（硬拦截，先于用户规则链）──
        if command:
            ok, reason = SecurityChecker.check_command(command)
            if not ok:
                self._render_security_deny(command, reason)
                return False

        for rule in self._rules:
            if not self._tool_match(rule.tool, tool):
                continue
            if rule.pattern not in command:
                continue

            if rule.action == "allow":
                return True
            if rule.action == "deny":
                self._render_deny(command, rule)
                return False
            if rule.action == "ask":
                return await self._confirm(command, rule)

        return True  # 无命中 → 放行

    @staticmethod
    def _tool_match(rule_tool: str, actual_tool: str) -> bool:
        return rule_tool == "*" or rule_tool == actual_tool

    # ── 渲染 ──

    @staticmethod
    def _render_deny(command: str, rule: GuardRule) -> None:
        console.print(Panel(
            f"[red]{command}[/red]\n"
            f"[dim]匹配规则: {rule.pattern} → deny[/dim]",
            title="⛔ 已拦截",
            border_style="red",
        ))

    @staticmethod
    def _render_security_deny(command: str, reason: str) -> None:
        console.print(Panel(
            f"[red]{command}[/red]\n"
            f"[dim]{reason}[/dim]",
            title="⛔ SecurityChecker 拦截",
            border_style="red",
        ))

    @staticmethod
    def _render_path_deny(path: str, reason: str) -> None:
        console.print(Panel(
            f"[red]{path}[/red]\n"
            f"[dim]{reason}[/dim]",
            title="⛔ 路径拦截",
            border_style="red",
        ))

    @staticmethod
    async def _confirm(command: str, rule: GuardRule) -> bool:
        console.print(Panel(
            f"[yellow]{command}[/yellow]\n"
            f"[dim]匹配: {rule.pattern}[/dim]",
            title="⚠️ 敏感命令",
            border_style="yellow",
        ))
        console.print(
            "[bold yellow]确认执行？[/bold yellow] [dim]y/N [/dim]", end="")
        resp = await asyncio.to_thread(input, "")
        return resp.strip().lower() in ("y", "yes")
