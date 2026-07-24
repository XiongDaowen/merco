"""Bash工具单元测试"""

import pytest

from merco.tools.bash_tools import BashTool


class TestBashTool:
    """BashTool 工具测试"""

    @pytest.fixture
    def bash_tool(self):
        tool = BashTool()
        yield tool
        # 测试结束后清理所有进程
        tool.kill_all()

    @pytest.mark.asyncio
    async def test_execute_simple_command(self, bash_tool):
        """测试执行简单命令"""
        result = await bash_tool.execute("echo 'hello world'")
        assert "error" not in result
        assert result["returncode"] == 0
        assert result["stdout"].strip() == "hello world"
        assert result["stderr"] == ""

    @pytest.mark.asyncio
    async def test_execute_command_with_stderr(self, bash_tool):
        """测试执行有stderr输出的命令"""
        result = await bash_tool.execute(">&2 echo 'error message'")
        assert "error" not in result
        assert result["returncode"] == 0
        assert result["stderr"].strip() == "error message"

    @pytest.mark.asyncio
    async def test_execute_command_with_non_zero_exit_code(self, bash_tool):
        """测试执行返回非零退出码的命令"""
        result = await bash_tool.execute("exit 123")
        assert "error" not in result
        assert result["returncode"] == 123

    @pytest.mark.asyncio
    async def test_execute_command_with_timeout(self, bash_tool):
        """测试命令执行超时"""
        result = await bash_tool.execute("sleep 2", timeout=0.5)
        assert "error" in result
        assert "timed out after 0.5s" in result["error"]

    @pytest.mark.asyncio
    async def test_execute_command_with_workdir(self, bash_tool, tmp_path):
        """测试指定工作目录执行命令"""
        # 在临时目录创建一个测试文件
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")

        # 在临时目录执行ls命令
        result = await bash_tool.execute("ls", workdir=str(tmp_path))
        assert "error" not in result
        assert result["returncode"] == 0
        assert "test.txt" in result["stdout"]

    @pytest.mark.asyncio
    async def test_execute_invalid_command(self, bash_tool):
        """测试执行不存在的命令"""
        result = await bash_tool.execute("nonexistent_command_12345")
        assert "error" not in result  # 错误会在stderr里
        assert result["returncode"] != 0
        assert "not found" in result["stderr"].lower()

    @pytest.mark.asyncio
    async def test_execute_command_with_non_utf8_output(self, bash_tool, tmp_path):
        """测试处理非UTF-8输出：二进制字节经 decode(errors='replace') 替换为 �。

        用 cat 二进制文件而非 printf 十六进制转义：/bin/sh（dash）的 printf
        不支持 \\x 转义，跨 shell 不稳；cat 文件不经 shell 转义，最可靠。
        """
        binary_file = tmp_path / "bin.dat"
        binary_file.write_bytes(b"\xff\xfe\xfd")  # 3 个无效 UTF-8 起始字节
        result = await bash_tool.execute(f"cat '{binary_file}'")
        assert "error" not in result
        assert result["returncode"] == 0
        # 0xff/0xfe/0xfd 均非合法 UTF-8 起始字节 -> decode(errors="replace") 产生 �
        assert "�" in result["stdout"]

    def test_kill_all_processes(self, bash_tool):
        """测试kill_all方法终止所有活跃进程"""

        # 手动添加一个模拟进程（不需要实际运行）
        class MockProcess:
            killed = False

            def kill(self):
                self.killed = True

        proc1 = MockProcess()
        proc2 = MockProcess()

        bash_tool._active_processes.add(proc1)
        bash_tool._active_processes.add(proc2)

        assert len(bash_tool._active_processes) == 2

        bash_tool.kill_all()

        assert proc1.killed is True
        assert proc2.killed is True
        assert len(bash_tool._active_processes) == 0

    @pytest.mark.asyncio
    async def test_process_lifecycle_management(self, bash_tool):
        """测试进程生命周期管理（活跃进程集合的添加和移除）"""
        assert len(bash_tool._active_processes) == 0

        # 执行一个短命令
        result = await bash_tool.execute("echo test")
        assert result["returncode"] == 0

        # 命令执行完毕后进程应该被移除
        assert len(bash_tool._active_processes) == 0
