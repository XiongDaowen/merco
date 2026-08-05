"""终端命令执行工具"""

import asyncio
import subprocess

from .base import BaseTool


class BashTool(BaseTool):
    """执行 bash 命令"""

    name = "bash"
    description = "在终端执行 shell 命令"
    toolset = "bash"
    parameters = {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "要执行的命令"},
            "timeout": {"type": "integer", "description": "超时时间（秒）"},
            "workdir": {"type": "string", "description": "工作目录"},
        },
        "required": ["command"],
    }

    def __init__(self):
        self._active_processes: set[asyncio.subprocess.Process] = set()

    async def execute(self, command: str, timeout: int = 60, workdir: str = None) -> dict:
        try:
            process = await asyncio.create_subprocess_shell(
                command,
                stdin=subprocess.DEVNULL,  # 不继承终端 stdin：交互式程序无法劫持 merco 输入
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=workdir,
                # 新会话：子进程 setsid() 后无控制终端，TUI 程序打开 /dev/tty 会失败，
                # 无法写转义序列污染 merco 终端。根因是控制终端共享（非 isatty）。
                start_new_session=True,
            )
            self._active_processes.add(process)

            try:
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
                return {
                    "stdout": stdout.decode("utf-8", errors="replace") if stdout else "",
                    "stderr": stderr.decode("utf-8", errors="replace") if stderr else "",
                    "returncode": process.returncode,
                }
            except TimeoutError:
                process.kill()
                return {"error": f"Command timed out after {timeout}s"}
            finally:
                self._active_processes.discard(process)

        except Exception as e:
            return {"error": str(e)}

    def kill_all(self):
        """终止所有活跃的子进程。"""
        for proc in self._active_processes:
            try:
                proc.kill()
            except ProcessLookupError:
                pass
        self._active_processes.clear()


from .registry import tool_registry  # noqa: E402 — 模块末尾自注册

tool_registry.register(BashTool())
