"""技能工具 — skill_view 让 LLM 按需加载技能完整内容"""

from .base import BaseTool


class SkillViewTool(BaseTool):
    """加载指定技能的完整说明文档

    对标 Hermes/OpenCode：LLM 调用 skill_view(name) 加载技能正文。
    工具描述动态列出可用技能，无需在 system prompt 中重复。
    """

    name = "skill_view"
    description = "加载指定技能的完整说明文档。使用前先调用此工具获取详细指引。"
    toolset = "skills"
    parameters = {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "技能名称（如 project-vision）",
            },
        },
        "required": ["name"],
    }

    def __init__(self):
        self._skill_registry = None

    def set_skill_registry(self, registry):
        """注入技能注册表（由 CLI 在构造 Agent 时调用）"""
        self._skill_registry = registry

    def describe(self, context: dict | None = None) -> str:
        """动态描述：列出所有可用技能的名称和简介"""
        base = self.description
        registry = self._skill_registry
        if registry:
            skills = registry.list_skills()
            if skills:
                lines = ["\n\n可用技能："]
                for s in skills:
                    lines.append(f"- **{s['name']}**: {s.get('description', '')}")
                base += "\n".join(lines)
        return base

    def check(self) -> bool:
        """有可用技能时才显示此工具"""
        return self._skill_registry is not None and len(self._skill_registry.list_skills()) > 0

    async def execute(self, name: str) -> dict:
        """返回技能的完整内容（正文 + 元数据）"""
        if not self._skill_registry:
            return {"error": "技能系统未初始化"}

        skill = self._skill_registry.get(name)
        if not skill:
            available = [s["name"] for s in self._skill_registry.list_skills()]
            return {
                "error": f"未找到技能: {name}",
                "available_skills": available,
            }

        return {
            "name": skill["name"],
            "description": skill.get("description", ""),
            "content": skill.get("content", ""),
        }


from .registry import tool_registry  # noqa: E402 — 模块末尾自注册

tool_registry.register(SkillViewTool())
