"""文件工具单元测试"""

import os
import tempfile

import pytest

from merco.tools.file_tools import ReadFile, WriteFile


class TestReadFile:
    """ReadFile 工具测试"""

    @pytest.fixture
    def read_tool(self):
        return ReadFile()

    @pytest.fixture
    def temp_test_file(self):
        """创建一个临时测试文件，内容是100行数字"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            for i in range(1, 101):
                f.write(f"line {i}\n")
            temp_path = f.name

        yield temp_path

        # 清理
        os.unlink(temp_path)

    @pytest.mark.asyncio
    async def test_read_nonexistent_file(self, read_tool):
        """测试读取不存在的文件"""
        result = await read_tool.execute("/nonexistent/path/file.txt")
        assert "error" in result
        assert "不存在" in result["error"]

    @pytest.mark.asyncio
    async def test_read_directory_instead_of_file(self, read_tool, tmp_path):
        """测试读取目录而非文件"""
        result = await read_tool.execute(str(tmp_path))
        assert "error" in result
        assert "不是文件" in result["error"]

    @pytest.mark.asyncio
    async def test_read_small_file_full(self, read_tool, temp_test_file):
        """测试读取完整小文件（<500行）"""
        result = await read_tool.execute(temp_test_file)
        assert "error" not in result
        assert result["start_line"] == 1
        assert result["end_line"] == 100
        assert result["has_more"] is False
        assert "line 1\nline 2\n" in result["content"]
        assert "line 100\n" in result["content"]

    @pytest.mark.asyncio
    async def test_read_with_offset_and_limit(self, read_tool, temp_test_file):
        """测试指定offset和limit读取"""
        result = await read_tool.execute(temp_test_file, offset=10, limit=20)
        assert "error" not in result
        assert result["start_line"] == 10
        assert result["end_line"] == 29  # 10到29共20行
        assert len(result["content"].splitlines()) == 20
        assert "line 10\n" in result["content"]
        assert "line 29\n" in result["content"]
        assert result["has_more"] is True  # 后面还有内容

    @pytest.mark.asyncio
    async def test_read_offset_exceeds_file_length(self, read_tool, temp_test_file):
        """测试offset超出文件范围"""
        result = await read_tool.execute(temp_test_file, offset=200)
        assert "error" not in result
        assert result["content"] == ""
        assert "超出文件范围" in result["hint"]

    @pytest.mark.asyncio
    async def test_read_with_head_parameter(self, read_tool, temp_test_file):
        """测试使用head参数读取前N行"""
        result = await read_tool.execute(temp_test_file, head=15)
        assert "error" not in result
        assert result["start_line"] == 1
        assert result["end_line"] == 15
        assert len(result["content"].splitlines()) == 15
        assert "line 1\n" in result["content"]
        assert "line 15\n" in result["content"]

    @pytest.mark.asyncio
    async def test_read_with_tail_parameter(self, read_tool, temp_test_file):
        """测试使用tail参数读取最后N行"""
        result = await read_tool.execute(temp_test_file, tail=10)
        assert "error" not in result
        assert result["lines"] == 10
        assert "文件最后 10 行" in result["hint"]
        content_lines = result["content"].splitlines()
        assert len(content_lines) == 10
        assert content_lines[0] == "line 91"
        assert content_lines[-1] == "line 100"

    @pytest.mark.asyncio
    async def test_read_large_file_pagination(self, read_tool):
        """测试大文件翻页功能"""
        # 创建一个600行的测试文件
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            for i in range(1, 601):
                f.write(f"line {i}\n")
            temp_path = f.name

        try:
            # 第一页（默认limit=500）
            page1 = await read_tool.execute(temp_path)
            assert page1["end_line"] == 500
            assert page1["has_more"] is True
            assert "用 offset=501 继续翻页" in page1["hint"]

            # 第二页
            page2 = await read_tool.execute(temp_path, offset=501)
            assert page2["start_line"] == 501
            assert page2["end_line"] == 600
            assert page2["has_more"] is False
        finally:
            os.unlink(temp_path)

    @pytest.mark.asyncio
    async def test_read_with_limit_zero_reads_all(self, read_tool, temp_test_file):
        """测试limit=0时读取整个文件"""
        result = await read_tool.execute(temp_test_file, limit=0)
        assert "error" not in result
        assert result["end_line"] == 100
        assert result["has_more"] is False
        assert len(result["content"].splitlines()) == 100

    @pytest.mark.asyncio
    async def test_read_non_utf8_file(self, read_tool):
        """测试读取非UTF-8编码文件（错误替换）"""
        # 创建一个包含非UTF-8字节的文件
        with tempfile.NamedTemporaryFile(mode="wb", suffix=".bin", delete=False) as f:
            f.write(b"valid utf8\n")
            f.write(b"\xff\xfe\xfd invalid bytes\n")  # 无效UTF-8
            f.write(b"more valid utf8\n")
            temp_path = f.name

        try:
            result = await read_tool.execute(temp_path)
            assert "error" not in result
            assert "valid utf8" in result["content"]
            assert "more valid utf8" in result["content"]
            # 无效字节会被替换为�
            assert "�" in result["content"]
        finally:
            os.unlink(temp_path)


class TestWriteFile:
    """WriteFile 工具测试"""

    @pytest.fixture
    def write_tool(self):
        return WriteFile()

    @pytest.mark.asyncio
    async def test_write_new_file(self, write_tool, tmp_path):
        """测试创建新文件并写入内容"""
        file_path = tmp_path / "new_file.txt"
        content = "hello world\n测试内容"

        result = await write_tool.execute(str(file_path), content)
        assert result["success"] is True
        assert result["path"] == str(file_path)

        # 验证文件内容
        assert file_path.read_text(encoding="utf-8") == content

    @pytest.mark.asyncio
    async def test_overwrite_existing_file(self, write_tool, tmp_path):
        """测试覆盖已有文件"""
        file_path = tmp_path / "existing.txt"
        file_path.write_text("old content")

        result = await write_tool.execute(str(file_path), "new content")
        assert result["success"] is True

        # 验证内容被覆盖
        assert file_path.read_text(encoding="utf-8") == "new content"

    @pytest.mark.asyncio
    async def test_write_to_nonexistent_directory(self, write_tool, tmp_path):
        """测试写入到不存在的目录（自动创建父目录）"""
        nested_path = tmp_path / "nested" / "dir" / "file.txt"
        content = "content in nested dir"

        result = await write_tool.execute(str(nested_path), content)
        assert result["success"] is True

        # 验证目录和文件都存在
        assert nested_path.exists()
        assert nested_path.read_text(encoding="utf-8") == content
