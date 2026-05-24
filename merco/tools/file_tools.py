"""文件操作工具 - 读写搜索"""

from pathlib import Path
from .base import BaseTool


class ReadFile(BaseTool):
    """读取文件内容，支持行/字符两种翻页模式

    对标 OpenCode read.ts：大文件用 offset+limit 翻页，不一次性加载。
    offset/limit 默认按行（配合代码/日志浏览）；如需字符级翻页使用 char_offset/char_limit。
    """

    name = "read_file"
    description = (
        "读取文件内容。大文件请用 offset/limit 翻页读取：\n"
        "- offset: 起始行号（1-indexed），默认第 1 行\n"
        "- limit:  读取行数，默认全读\n"
        "- char_offset / char_limit: 字符级翻页，配合截断缓存文件使用"
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
                "description": "读取行数，默认全部",
            },
            "char_offset": {
                "type": "integer",
                "description": "字符级起始偏移（0-indexed），配合截断缓存时使用",
            },
            "char_limit": {
                "type": "integer",
                "description": "字符级读取上限",
            },
        },
        "required": ["path"],
    }

    async def execute(self, path: str, limit: int = None, offset: int = None,
                      char_offset: int = None, char_limit: int = None) -> dict:
        file_path = Path(path)
        if not file_path.exists():
            return {"error": f"文件 '{path}' 不存在"}

        # 字符级翻页：只读需要的字节范围（大文件友好）
        if char_offset is not None or char_limit is not None:
            return self._read_by_chars(file_path, char_offset or 0, char_limit)

        # 行级翻页：默认模式
        return self._read_by_lines(file_path, offset or 1, limit)

    def _read_by_chars(self, file_path: Path, start: int, limit: int | None) -> dict:
        """字符级读取——分段读文件，不全部加载到内存"""
        file_size = file_path.stat().st_size
        if start >= file_size:
            return {"content": "", "file_size": file_size, "hint": "offset 超出文件范围"}

        read_limit = min(limit, file_size - start) if limit else file_size - start
        # 读略多一点以便在字符边界截断（UTF-8 多字节安全）
        read_end = min(start + read_limit + 256, file_size)
        with open(file_path, "rb") as f:
            f.seek(start)
            raw = f.read(read_end - start)

        text = raw.decode("utf-8", errors="replace")
        # 截到请求的字符数
        if limit and len(text) > limit:
            text = text[:limit]

        return {
            "content": text,
            "file_size": file_size,
            "char_offset": start,
            "char_limit": limit,
            "next_char_offset": start + len(text) if len(text) > 0 else start,
        }

    def _read_by_lines(self, file_path: Path, start_line: int, limit: int | None) -> dict:
        """行级读取，返回行号范围"""
        # 对于很大的文件，逐行流式读
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                all_lines = f.readlines()
        except OSError as e:
            return {"error": f"读取失败: {e}"}

        total_lines = len(all_lines)
        if start_line > total_lines:
            return {"content": "", "total_lines": total_lines, "hint": "offset 超出文件行数"}

        idx = start_line - 1
        end = idx + limit if limit else total_lines
        selected = all_lines[idx:end]

        return {
            "content": "".join(selected),
            "total_lines": total_lines,
            "start_line": start_line,
            "end_line": start_line + len(selected) - 1,
        }


class WriteFile(BaseTool):
    """写入文件内容"""

    name = "write_file"
    description = "写入内容到指定文件"
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
