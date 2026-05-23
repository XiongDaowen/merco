"""文件操作工具 - 读写搜索"""

from pathlib import Path
from .base import BaseTool


class ReadFile(BaseTool):
    """读取文件内容"""

    name = "read_file"
    description = "读取指定文件的内容"
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "文件路径"},
            "limit": {"type": "integer", "description": "读取行数限制"},
            "offset": {"type": "integer", "description": "起始行号 (1-indexed)"},
        },
        "required": ["path"],
    }

    async def execute(self, path: str, limit: int = None, offset: int = None) -> dict:
        file_path = Path(path)
        if not file_path.exists():
            return {"error": f"File not found: {path}"}

        content = file_path.read_text()
        lines = content.splitlines()

        if offset and offset > 0:
            lines = lines[offset - 1:]
        if limit:
            lines = lines[:limit]

        return {"content": "\n".join(lines), "total_lines": len(lines)}


class WriteFile(BaseTool):
    """写入文件内容"""

    name = "write_file"
    description = "写入内容到指定文件"
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
