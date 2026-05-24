"""沙箱隔离机制"""

import os
import tempfile
from pathlib import Path


class SandboxIsolation:
    """提供执行隔离环境"""

    def __init__(self, work_dir: str = None):
        self.work_dir = work_dir or tempfile.mkdtemp(prefix="merco_")
        self.allowed_dirs: list[str] = []

    def allow_directory(self, path: str, read_only: bool = False):
        """允许访问指定目录"""
        self.allowed_dirs.append({"path": path, "read_only": read_only})

    def is_path_allowed(self, path: str, write: bool = False) -> bool:
        """检查路径是否允许访问"""
        target = Path(path).resolve()

        for allowed in self.allowed_dirs:
            allowed_path = Path(allowed["path"]).resolve()
            if target == allowed_path or target.is_relative_to(allowed_path):
                if write and allowed["read_only"]:
                    return False
                return True

        return False

    def cleanup(self):
        """清理临时工作目录"""
        import shutil
        if self.work_dir.startswith("/tmp"):
            shutil.rmtree(self.work_dir, ignore_errors=True)
