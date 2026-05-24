"""技能注册与管理"""

from typing import Optional


class SkillRegistry:
    """技能注册表"""

    def __init__(self):
        self._skills: dict[str, dict] = {}

    def register(self, skill: dict):
        """注册技能"""
        self._skills[skill["name"]] = skill

    def unregister(self, name: str):
        """注销技能"""
        self._skills.pop(name, None)

    def get(self, name: str) -> Optional[dict]:
        """获取技能"""
        return self._skills.get(name)

    def list_skills(self) -> list[dict]:
        """列出所有技能"""
        return list(self._skills.values())

    def get_relevant(self, query: str) -> list[dict]:
        """根据查询获取相关技能（简单关键词匹配）"""
        query_lower = query.lower()
        relevant = []

        for skill in self._skills.values():
            desc = skill.get("description", "").lower()
            name = skill.get("name", "").lower()
            if query_lower in desc or query_lower in name:
                relevant.append(skill)

        return relevant

    def load_from_paths(self, paths: list[str]):
        """从多个路径加载技能"""
        from .loader import SkillLoader

        for path in paths:
            skills = SkillLoader.load_from_directory(path)
            for skill in skills:
                self.register(skill)
