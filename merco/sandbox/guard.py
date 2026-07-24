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
from abc import ABC, abstractmethod
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
    """工具执行守卫 — facade，委托给 PolicyPipeline

    用法::

        guard = ToolGuard()
        guard.rule("bash", "DROP TABLE", "deny")

        result = await guard.check("bash", {"command": "rm file.txt"})
        if result.action == GuardAction.DENY:
            return  # 已拦截

    插件用法::

        pipeline = PolicyPipeline()
        pipeline.use(BuiltinDefaultPolicy(mode="ask"))
        pipeline.use(MyCustomPolicy())
        guard = ToolGuard(pipeline=pipeline)
    """

    def __init__(self, pipeline: "PolicyPipeline" = None, mode: str = "ask", user_rules: list = None):
        if pipeline:
            self._pipeline = pipeline
        else:
            # 向后兼容：没传 pipeline 时自动创建默认 pipeline
            self._pipeline = PolicyPipeline()
            self._pipeline.use(BuiltinDefaultPolicy(mode=mode, user_rules=user_rules))

    def rule(self, tool: str, pattern: str, action: str) -> "ToolGuard":
        """添加规则（向后兼容）。在默认策略前插入一条自定义策略。"""
        self._pipeline._policies.insert(0,
            _SingleRulePolicy(tool, pattern, action))
        return self

    async def check(self, tool_name: str, arguments: dict) -> GuardResult:
        return await self._pipeline.check(tool_name, arguments)


# ── PermissionPolicy ───────────────────────────────────────

class PermissionPolicy(ABC):
    """安全策略基类"""
    name: str = ""

    @abstractmethod
    async def check(self, tool_name: str, arguments: dict) -> GuardResult | None:
        """检查工具。返回 GuardResult = 决断，None = 传给下一个策略"""
        ...


class PolicyPipeline:
    """安全策略责任链"""

    def __init__(self):
        self._policies: list[PermissionPolicy] = []

    def use(self, policy: PermissionPolicy) -> "PolicyPipeline":
        """注册策略"""
        self._policies.append(policy)
        return self

    async def check(self, tool_name: str, arguments: dict) -> GuardResult:
        """依次检查，首个返回非 None 的结果生效"""
        for policy in self._policies:
            result = await policy.check(tool_name, arguments)
            if result is not None:
                return result
        return GuardResult(action=GuardAction.ALLOW, command="")


class _SingleRulePolicy(PermissionPolicy):
    """单条规则的策略包装"""
    name = "single_rule"

    def __init__(self, tool, pattern, action):
        self._tool = tool
        self._pattern = pattern
        self._action = action

    async def check(self, tool_name, arguments):
        command = arguments.get("command", "")
        if self._tool not in (tool_name, "*"):
            return None
        if self._pattern not in command:
            return None
        return GuardResult(action=GuardAction(self._action), command=command)


# ── BuiltinDefaultPolicy ───────────────────────────────────

class BuiltinDefaultPolicy(PermissionPolicy):
    """默认安全策略 — 包装 30 条默认规则 + SecurityChecker + mode logic"""
    name = "builtin_default"

    def __init__(self, mode: str = "ask", user_rules: list = None):
        self.mode = mode
        self._rules: list[GuardRule] = []
        if user_rules:
            for r in user_rules:
                self._rules.append(
                    GuardRule.from_dict(r) if isinstance(r, dict) else r
                )
        self._rules.extend(_DEFAULT_RULES)

    async def check(self, tool_name: str, arguments: dict) -> GuardResult | None:
        if self.mode == "auto":
            return GuardResult(action=GuardAction.ALLOW, command="")

        command = arguments.get("command", "")
        path = arguments.get("path", "")

        if path and tool_name != "bash":
            ok, reason = SecurityChecker.check_file_path(path)
            if not ok:
                return GuardResult(action=GuardAction.DENY, command=path, reason=reason)

        if command:
            ok, reason = SecurityChecker.check_command(command)
            if not ok:
                return GuardResult(action=GuardAction.DENY, command=command, reason=reason)

        for rule in self._rules:
            if not self._tool_match(rule.tool, tool_name):
                continue
            if rule.pattern not in command:
                continue
            action = GuardAction(rule.action)
            return GuardResult(action=action, command=command, rule=rule)

        return GuardResult(action=GuardAction.ALLOW, command=command)

    @staticmethod
    def _tool_match(pattern: str, tool_name: str) -> bool:
        return pattern == "*" or pattern == tool_name
