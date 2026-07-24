"""文件编辑工具 — EditFile (SEARCH/REPLACE)"""

import difflib
import logging
from pathlib import Path

from .base import BaseTool
from .registry import tool_registry

logger = logging.getLogger("merco.tools.edit")


def _generate_diff(filepath: str, old: str, new: str) -> str:
    """生成 unified diff 文本"""
    diff_lines = list(difflib.unified_diff(
        old.splitlines(keepends=True),
        new.splitlines(keepends=True),
        fromfile=filepath,
        tofile=filepath,
    ))
    return "".join(diff_lines)


def _validate_search(content: str, search: str, path: str) -> str | None:
    """校验 SEARCH 内容是否唯一存在于文件中。返回错误信息或 None。"""
    count = content.count(search)
    if count == 0:
        return f"在 `{path}` 中**未找到**匹配内容：\n```\n{search}\n```"
    if count > 1:
        return f"在 `{path}` 中找到 **{count} 处**匹配，`search` 内容必须唯一"
    return None


# ── EditFile ────────────────────────────────────────────────────────

class EditFile(BaseTool):
    """编辑文件内容 — SEARCH/REPLACE 模式，含 diff 预览和确认"""

    name = "edit_file"
    description = (
        "🔧 修改已有文件的首选工具。用 SEARCH/REPLACE 块精准替换：\n"
        "- search: 文件中的原内容（必须唯一）\n"
        "- replace: 替换后的内容\n\n"
        "会展示 diff 预览并等待用户确认。如需创建新文件请用 write_file。"
    )
    toolset = "file"
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "文件路径",
            },
            "search": {
                "type": "string",
                "description": "文件中的原内容，必须唯一",
            },
            "replace": {
                "type": "string",
                "description": "替换后的内容",
            },
        },
        "required": ["path", "search", "replace"],
    }

    async def execute(self, path: str, search: str, replace: str) -> dict:
        """edit_file

        Args:
            path: 文件路径
            search: 原内容（必须唯一）
            replace: 新内容
        """
        file_path = Path(path)
        if not file_path.exists():
            return {"error": f"文件 '{path}' 不存在"}

        old_content = file_path.read_text(encoding="utf-8")

        # 校验 SEARCH 唯一性
        err = _validate_search(old_content, search, path)
        if err:
            return {"error": err}

        # 执行替换
        new_content = old_content.replace(search, replace, 1)
        diff_text = _generate_diff(path, old_content, new_content)

        if not diff_text.strip():
            return {"success": True, "path": path,
                    "message": "文件内容无变化", "diff": ""}

        return {
            "planned_edit": True,
            "path": path,
            "old_content": old_content,
            "new_content": new_content,
            "diff": diff_text,
        }


# ── 自注册 ──
tool_registry.register(EditFile())
