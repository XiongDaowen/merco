"""安全检查"""

import re


class SecurityChecker:
    """检查命令与内容的安全性"""

    DANGEROUS_PATTERNS = [
        r"rm\s+-rf\s+/",
        r"mkfs",
        r"dd\s+if=",
        r">\s*/dev/sd",
        r"chmod\s+777\s+/",
        r"wget.*\|\s*bash",
        r"curl.*\|\s*sh",
    ]

    @classmethod
    def check_command(cls, command: str) -> tuple[bool, str]:
        """检查命令是否危险"""
        for pattern in cls.DANGEROUS_PATTERNS:
            if re.search(pattern, command, re.IGNORECASE):
                return False, f"Dangerous pattern detected: {pattern}"
        return True, ""

    @classmethod
    def check_file_path(cls, path: str) -> tuple[bool, str]:
        """检查文件路径是否安全"""
        if ".." in path:
            return False, "Path traversal detected"
        if path.startswith("/proc") or path.startswith("/sys"):
            return False, "Access to system paths not allowed"
        return True, ""
