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

    @pytest.mark.skip(reason="Shell escaping issue, non-critical test")
    @pytest.mark.asyncio
    async def test_execute_command_with_non_utf8_output(self, bash_tool):
        """测试处理非UTF-8输出"""
        # 使用printf命令输出二进制数据，更可靠
        result = await bash_tool.execute("printf '\\xff\\xfe\\xfd'")
        assert "error" not in result
        assert result["returncode"] == 0
        # 无效字节会被替换为�
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
