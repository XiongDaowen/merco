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

import logging
from dataclasses import dataclass
from enum import Enum

from .security import SecurityChecker

logger = logging.getLogger("merco.guard")


# ── 枚举和结果 ──────────────────────────────────────────────

class GuardAction(Enum):
    ALLOW = "allow"      # 直接放行
    DENY = "deny"        # 直接拒绝
    ASK = "ask"          # 需要用户确认

@dataclass
class GuardResult:
    action: GuardAction
    command: str
    rule: "GuardRule | None" = None
    reason: str = ""


class GuardConfirmationRequired(Exception):
    """需要用户确认才能继续执行"""

    def __init__(self, result: GuardResult):
        self.result = result
        super().__init__(f"需要确认: {result.command} - {result.reason}")


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

        result = await guard.check("bash", {"command": "rm file.txt"})
        if result.action == GuardAction.DENY:
            return  # 已拦截
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

    async def check(self, tool_name: str, arguments: dict) -> GuardResult:
        """检查工具是否可以执行。返回 GuardResult。"""
        if self.mode == "auto":
            return GuardResult(action=GuardAction.ALLOW, command="")

        command = arguments.get("command", "")
        path = arguments.get("path", "")

        # 文件工具：SecurityChecker 路径检测
        if path and tool_name != "bash":
            ok, reason = SecurityChecker.check_file_path(path)
            if not ok:
                return GuardResult(
                    action=GuardAction.DENY,
                    command=path,
                    reason=reason
                )

        # SecurityChecker 正则兜底
        if command:
            ok, reason = SecurityChecker.check_command(command)
            if not ok:
                return GuardResult(
                    action=GuardAction.DENY,
                    command=command,
                    reason=reason
                )

        # 规则链匹配
        for rule in self._rules:
            if not self._tool_match(rule.tool, tool_name):
                continue
            if rule.pattern not in command:
                continue

            if rule.action == "allow":
                return GuardResult(action=GuardAction.ALLOW, command=command, rule=rule)
            if rule.action == "deny":
                return GuardResult(action=GuardAction.DENY, command=command, rule=rule)
            if rule.action == "ask":
                return GuardResult(action=GuardAction.ASK, command=command, rule=rule)

        return GuardResult(action=GuardAction.ALLOW, command=command)

    @staticmethod
    def _tool_match(rule_tool: str, actual_tool: str) -> bool:
        """检查规则工具是否匹配实际工具。"""
        return rule_tool == "*" or rule_tool == actual_tool