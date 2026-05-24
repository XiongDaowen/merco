"""权限控制"""

import fnmatch
from typing import Optional


class PermissionManager:
    """管理工具与命令的访问权限"""

    def __init__(self, mode: str = "ask"):
        """
        mode: "allow" | "ask" | "deny"
        """
        self.mode = mode
        self._rules: dict[str, dict] = {}

    def set_mode(self, mode: str):
        """设置默认权限模式"""
        if mode not in ("allow", "ask", "deny"):
            raise ValueError(f"Invalid mode: {mode}")
        self.mode = mode

    def add_rule(self, tool: str, pattern: str, action: str):
        """添加权限规则"""
        if tool not in self._rules:
            self._rules[tool] = {}
        self._rules[tool][pattern] = action

    def check(self, tool: str, command: str = None) -> str:
        """检查权限，返回 allow/ask/deny"""
        tool_rules = self._rules.get(tool, {})

        # 最后匹配的规则生效
        for pattern, action in tool_rules.items():
            if command is None or fnmatch.fnmatch(command, pattern):
                return action

        return self.mode

    def is_allowed(self, tool: str, command: str = None) -> bool:
        """检查是否允许执行"""
        return self.check(tool, command) == "allow"

    def needs_approval(self, tool: str, command: str = None) -> bool:
        """检查是否需要用户确认"""
        return self.check(tool, command) == "ask"
