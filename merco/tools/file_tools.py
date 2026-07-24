"""文件操作工具 — 流式行读，支持 head/tail/翻页"""

import logging
from collections import deque
from pathlib import Path

from .base import BaseTool

logger = logging.getLogger("merco.tools.file")

_DEFAULT_LIMIT = 500  # 默认读取上限（行），覆盖大多数源文件，大文件用 offset 翻页


class ReadFile(BaseTool):
    """流式行读取 — 大文件不爆内存，默认上限防上下文溢出"""

    name = "read_file"
    description = (
        "读取文件内容，默认返回前 500 行。大文件请用 offset/limit 翻页。\n"
        "- offset: 起始行号（1-indexed），默认第 1 行\n"
        "- limit:  读取行数，默认 500，设 0 表示不设上限（慎用）\n"
        "- head:   读前 N 行，等价 offset=1, limit=N\n"
        "- tail:   读最后 N 行"
    )
    toolset = "file"
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "文件路径",
            },
            "offset": {
                "type": "integer",
                "description": "起始行号（1-indexed），默认 1",
            },
            "limit": {
                "type": "integer",
                "description": "读取行数，默认 500。设 0 取消上限（仅小文件）",
            },
            "head": {
                "type": "integer",
                "description": "读前 N 行，等价 offset=1, limit=N",
            },
            "tail": {
                "type": "integer",
                "description": "读最后 N 行",
            },
        },
        "required": ["path"],
    }

    async def execute(self, path: str, limit: int = None, offset: int = None,
                      head: int = None, tail: int = None) -> dict:
        file_path = Path(path)
        if not file_path.exists():
            return {"error": f"文件 '{path}' 不存在"}
        if not file_path.is_file():
            return {"error": f"'{path}' 不是文件"}

        # ── 参数解析 ──
        if tail is not None:
            return self._read_tail(file_path, tail)

        if head is not None:
            offset = 1
            limit = head

        start_line = offset or 1
        if start_line < 1:
            start_line = 1

        if limit is None:
            limit = _DEFAULT_LIMIT
        elif limit == 0:
            limit = None  # 0 = 不设上限
        elif limit < 0:
            limit = _DEFAULT_LIMIT

        return self._read_by_lines(file_path, start_line, limit)

    # ── 流式行读（不一次性加载全文件） ──

    def _read_by_lines(self, file_path: Path, start_line: int, limit: int | None) -> dict:
        """从 start_line 开始逐行读取，读到 limit 行或 EOF 即停"""
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                # 跳过 start_line - 1 行
                for _ in range(start_line - 1):
                    if not f.readline():
                        return {
                            "content": "",
                            "hint": f"offset {start_line} 超出文件范围",
                        }

                lines: list[str] = []
                for line in f:
                    lines.append(line)
                    if limit is not None and len(lines) >= limit:
                        break

                # 探测是否还有更多内容
                has_more = bool(f.readline()) if limit is not None else False
        except OSError as e:
            return {"error": f"读取失败: {e}"}

        content = "".join(lines)
        end_line = start_line + len(lines) - 1
        mtime = file_path.stat().st_mtime

        hint = "" if not has_more else (
            f"已返回 {start_line}-{end_line} 行，文件未完。"
            f"用 offset={end_line + 1} 继续翻页。"
        )

        return {
            "content": content,
            "start_line": start_line,
            "end_line": end_line,
            "has_more": has_more,
            "hint": hint,
            "mtime": mtime,
        }

    # ── 读尾部 N 行 ──

    def _read_tail(self, file_path: Path, n: int) -> dict:
        """读取文件最后 N 行 — 用固定大小的双端队列，内存 O(n)"""
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                last_n = deque(f, maxlen=n)
        except OSError as e:
            return {"error": f"读取失败: {e}"}

        content = "".join(last_n)
        mtime = file_path.stat().st_mtime

        return {
            "content": content,
            "lines": len(last_n),
            "hint": f"文件最后 {len(last_n)} 行",
            "mtime": mtime,
        }


class WriteFile(BaseTool):
    """写入文件内容"""

    name = "write_file"
    description = (
        "创建新文件或完全覆盖已有文件。\n"
        "⚠️ 仅用于新建文件。修改已有文件请用 edit_file（SEARCH/REPLACE），"
        "它会展示 diff 并等待确认。"
    )
    toolset = "file"
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "文件路径"},
            "content": {"type": "string", "description": "写入内容"},
        },
        "required": ["path", "content"],
    }

    async def execute(self, path: str, content: str) -> dict:
        file_path = Path(path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content)
        return {"success": True, "path": str(path)}


from .registry import tool_registry  # noqa: E402 — 模块末尾自注册

tool_registry.register(ReadFile())
tool_registry.register(WriteFile())
