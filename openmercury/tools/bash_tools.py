"""终端命令执行工具"""

import asyncio
import subprocess
from .base import BaseTool


class BashTool(BaseTool):
    """执行 bash 命令"""

    name = "bash"
    description = "在终端执行 shell 命令"
    parameters = {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "要执行的命令"},
            "timeout": {"type": "integer", "description": "超时时间（秒）"},
            "workdir": {"type": "string", "description": "工作目录"},
        },
        "required": ["command"],
    }

    async def execute(self, command: str, timeout: int = 60, workdir: str = None) -> dict:
        try:
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=workdir,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(), timeout=timeout
                )
                return {
                    "stdout": stdout.decode("utf-8", errors="replace") if stdout else "",
                    "stderr": stderr.decode("utf-8", errors="replace") if stderr else "",
                    "returncode": process.returncode,
                }
            except asyncio.TimeoutError:
                process.kill()
                return {"error": f"Command timed out after {timeout}s"}

        except Exception as e:
            return {"error": str(e)}
