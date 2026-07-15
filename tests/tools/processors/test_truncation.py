"""截断处理器单元测试"""
import json
import os
import tempfile
import time
from unittest.mock import patch, MagicMock
import pytest
from merco.tools.processors.truncation import TruncationProcessor
from merco.core.pipeline import ProcessContext


class TestTruncationProcessor:
    """TruncationProcessor 测试"""

    @pytest.fixture
    def temp_trunc_dir(self):
        """临时截断目录"""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir
            # 重置类变量
            TruncationProcessor._last_cleanup = 0.0

    @pytest.fixture
    def processor(self, temp_trunc_dir):
        """创建处理器实例，使用临时目录"""
        return TruncationProcessor(
            max_bytes=1000,  # 小阈值方便测试
            trunc_dir=temp_trunc_dir
        )

    @pytest.fixture
    def small_result_ctx(self):
        """小结果上下文（不需要截断）"""
        return ProcessContext(
            tool_name="test_tool",
            arguments={},
            result={"data": "small content", "status": "ok"}
        )

    @pytest.fixture
    def large_result_ctx(self):
        """大结果上下文（需要截断）"""
        large_data = "x" * 2000  # 超过max_bytes=1000
        return ProcessContext(
            tool_name="test_tool",
            arguments={},
            result={"data": large_data, "status": "ok", "other": "additional info"}
        )

    @pytest.mark.asyncio
    async def test_small_result_no_truncation(self, processor, small_result_ctx):
        """测试小结果不截断"""
        result = await processor.process(small_result_ctx)

        assert result is False  # 没有修改结果
        assert "_truncated" not in small_result_ctx.result

    @pytest.mark.asyncio
    async def test_large_result_truncation(self, processor, large_result_ctx, temp_trunc_dir):
        """测试大结果正常截断并写入文件"""
        result = await processor.process(large_result_ctx)

        assert result is False
        assert large_result_ctx.result["_truncated"] is True
        assert "_full_output_path" in large_result_ctx.result
        assert "_pagination" in large_result_ctx.result
        assert "_hint" in large_result_ctx.result

        # 检查文件是否创建
        file_path = large_result_ctx.result["_full_output_path"]
        assert os.path.exists(file_path)
        assert file_path.startswith(temp_trunc_dir)

        # 检查文件内容
        with open(file_path, "r", encoding="utf-8") as f:
            saved_data = json.load(f)
            assert saved_data["data"] == "x" * 2000
            assert saved_data["status"] == "ok"

    @pytest.mark.asyncio
    async def test_result_exceed_max_file_size(self, processor):
        """测试结果超过文件大小上限，不写入文件"""
        processor.max_file_bytes = 1000  # 小上限
        large_data = "x" * 2000
        ctx = ProcessContext(
            tool_name="test_tool",
            arguments={},
            result={"data": large_data}
        )

        await processor.process(ctx)

        assert ctx.result["_truncated"] is True
        assert "_full_output_path" not in ctx.result  # 超过上限不写文件
        assert "超过缓存上限" in ctx.result["_hint"]

    @pytest.mark.asyncio
    async def test_reading_trunc_file_prevent_nested_write(self, processor, large_result_ctx, temp_trunc_dir):
        """测试读取截断文件时，不嵌套写入新的截断文件"""
        # 标记为正在读取截断文件（设置 arguments.path 指向 trunc_dir）
        large_result_ctx.arguments["path"] = os.path.join(temp_trunc_dir, "some_trunc_file.json")

        await processor.process(large_result_ctx)

        assert large_result_ctx.result["_truncated"] is True
        assert "_full_output_path" not in large_result_ctx.result  # 没有写入文件
        assert "截断缓存文件" in large_result_ctx.result["_hint"]

    @pytest.mark.asyncio
    async def test_non_serializable_result_skipped(self, processor):
        """测试无法序列化的结果不截断"""
        # 创建包含无法序列化的对象的结果
        class NonSerializable:
            pass

        ctx = ProcessContext(
            tool_name="test_tool",
            arguments={},
            result={"data": NonSerializable()}
        )

        result = await processor.process(ctx)
        assert result is False
        assert "_truncated" not in ctx.result

    @pytest.mark.asyncio
    async def test_write_failure_handled(self, processor, large_result_ctx, caplog):
        """测试写入失败时的错误处理"""
        # 模拟写入失败
        with patch("pathlib.Path.write_text", side_effect=OSError("Permission denied")):
            result = await processor.process(large_result_ctx)

            assert result is False
            # 写入失败时不设置 _truncated（文件未成功保存）
            assert "_truncated" not in large_result_ctx.result
            # 应该有警告日志
            assert any("截断文件写入失败" in record.message for record in caplog.records)

    def test_trunc_dir_default(self):
        """测试默认截断目录路径"""
        processor = TruncationProcessor()
        default_dir = os.path.expanduser("~/.merco/trunc")
        assert processor.trunc_dir == default_dir

    def test_maybe_cleanup(self, processor, temp_trunc_dir):
        """测试懒清理过期文件"""
        # 创建一些测试文件
        now = time.time()
        old_file = os.path.join(temp_trunc_dir, "12345_test.json")
        new_file = os.path.join(temp_trunc_dir, "67890_test.json")

        # 创建文件并修改mtime
        with open(old_file, "w") as f:
            f.write("{}")
        os.utime(old_file, (now - 8 * 86400, now - 8 * 86400))  # 8天前，过期

        with open(new_file, "w") as f:
            f.write("{}")
        os.utime(new_file, (now - 1 * 86400, now - 1 * 86400))  # 1天前，不过期

        # 执行清理
        processor._maybe_cleanup()

        # 检查旧文件被删除，新文件保留
        assert not os.path.exists(old_file)
        assert os.path.exists(new_file)

        # 第二次清理应该跳过，因为间隔不够
        with patch("os.listdir") as mock_listdir:
            processor._maybe_cleanup()
            mock_listdir.assert_not_called()

    def test_maybe_cleanup_directory_not_exist(self):
        """测试目录不存在时清理不报错"""
        # 创建一个 processor，其 trunc_dir 路径不存在
        import tempfile
        nonexistent = os.path.join(tempfile.gettempdir(), "merco_test_nonexistent_dir_xyz")
        processor = TruncationProcessor(trunc_dir=nonexistent)
        assert not os.path.exists(processor.trunc_dir)
        # 清理应该不报错
        processor._maybe_cleanup()
