"""Skill-related result processors."""

from __future__ import annotations

import logging

from merco.core.pipeline import ProcessContext, Processor

logger = logging.getLogger("merco.pipeline")


class SkillViewProcessor(Processor):
    """Skill 注入：skill_view 结果以 user message 注入上下文。

    对标 Hermes：skill 内容以 role=user 注入（高优先级 + prompt cache 友好）。
    不追加到 system prompt（跨 provider 兼容更好）。
    """

    name = "skill_view"

    async def process(self, ctx: ProcessContext) -> bool:
        if ctx.tool_name != "skill_view":
            return False
        if "error" in ctx.result:
            return False
        if "content" not in ctx.result:
            return False

        skill_name = ctx.result.get("name", "unknown")
        skill_content = ctx.result["content"]
        content_len = len(skill_content)

        # 工具结果只留占位信息
        ctx.result["content"] = f"技能 {skill_name} 已加载（{content_len:,} 字符），详见上下文。"

        # 完整内容以 user message 注入
        user_msg = f"技能 **{skill_name}** 已加载，请遵循以下指引：\n\n{skill_content}"
        # 仍然截断保护：user message 上限 8000
        if len(user_msg) > 8000:
            user_msg = user_msg[:7800] + "\n\n...(技能内容过长，已截断)"

        ctx.extra_messages.append(
            {
                "role": "user",
                "content": user_msg,
            }
        )

        return False  # 不停止管线
