"""内置技能 — 随 merco 包分发，安装时复制到用户全局 skills 目录"""

import os
import shutil
from pathlib import Path

_BUILTIN_DIR = Path(__file__).resolve().parent
_INSTALL_TARGETS = [
    os.path.expanduser("~/.config/merco/skills"),
    os.path.expanduser("~/.merco/skills"),
]


def install_builtin_skills(force: bool = False) -> list[str]:
    """将内置技能复制到用户全局 skills 目录。返回已安装的技能名列表。

    - 如果目标已存在同名技能且未传 force=True，则跳过
    - 默认安装到 ~/.config/merco/skills/
    """
    installed: list[str] = []
    target = _INSTALL_TARGETS[0]  # 全局配置优先
    os.makedirs(target, exist_ok=True)

    for entry in _BUILTIN_DIR.iterdir():
        if not entry.is_dir() or entry.name.startswith("_") or entry.name.startswith("."):
            continue
        skill_file = entry / "SKILL.md"
        if not skill_file.exists():
            continue

        dest_dir = Path(target) / entry.name
        dest_file = dest_dir / "SKILL.md"

        if not force and dest_file.exists():
            continue

        # 目录可能含子文件（如 references/），整目录覆盖
        if dest_dir.exists():
            shutil.rmtree(dest_dir)
        shutil.copytree(entry, dest_dir)
        installed.append(entry.name)

    return installed
