"""审计日志"""

import json
import time
from pathlib import Path


class AuditLogger:
    """记录安全与操作审计日志"""

    def __init__(self, log_path: str = None):
        self.log_path = Path(log_path or "~/.openmercury/audit.log").expanduser()
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def log(self, action: str, user: str, details: dict = None):
        """记录审计事件"""
        entry = {
            "timestamp": time.time(),
            "action": action,
            "user": user,
            "details": details or {},
        }

        with open(self.log_path, "a") as f:
            f.write(json.dumps(entry) + "\n")

    def read(self, limit: int = 100) -> list[dict]:
        """读取最近的审计日志"""
        if not self.log_path.exists():
            return []

        entries = []
        with open(self.log_path) as f:
            for line in f:
                line = line.strip()
                if line:
                    entries.append(json.loads(line))

        return entries[-limit:]
