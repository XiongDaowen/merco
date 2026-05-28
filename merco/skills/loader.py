"""技能加载器 - 从文件系统加载 SKILL.md"""

import re
from pathlib import Path
from typing import Optional


class SkillLoader:
    """从目录加载技能"""

    SKILL_FILE = "SKILL.md"

    @classmethod
    def load_from_path(cls, path: str) -> Optional[dict]:
        """从路径加载单个技能"""
        skill_path = Path(path).expanduser() / cls.SKILL_FILE
        if not skill_path.exists():
            return None

        content = skill_path.read_text()
        return cls._parse_skill(content)

    @classmethod
    def load_from_directory(cls, directory: str) -> list[dict]:
        """从目录递归加载所有技能"""
        skills = []
        base = Path(directory).expanduser()

        if not base.exists():
            return skills

        for skill_dir in base.rglob("*"):
            if skill_dir.is_dir() and (skill_dir / cls.SKILL_FILE).exists():
                skill = cls.load_from_path(str(skill_dir))
                if skill:
                    skills.append(skill)

        return skills

    @classmethod
    def _parse_skill(cls, content: str) -> dict:
        """解析技能文件（支持 frontmatter）"""
        # 提取 frontmatter
        frontmatter_match = re.match(r"^---\n(.*?)\n---\n(.*)", content, re.DOTALL)

        if frontmatter_match:
            frontmatter_str = frontmatter_match.group(1)
            body = frontmatter_match.group(2).strip()

            # 简单解析 YAML-like frontmatter
            frontmatter = {}
            for line in frontmatter_str.splitlines():
                if ":" in line:
                    key, value = line.split(":", 1)
                    frontmatter[key.strip()] = value.strip()

            return {
                "name": frontmatter.get("name", "unknown"),
                "description": frontmatter.get("description", ""),
                "content": body,
                "metadata": frontmatter,
            }

        return {
            "name": Path(content[:50]).stem if content else "unknown",
            "description": "",
            "content": content,
            "metadata": {},
        }
