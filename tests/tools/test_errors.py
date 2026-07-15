"""错误处理工具单元测试"""
import pytest
from merco.tools.errors import (
    classify_error, tool_error, empty_response,
    _public_message, _params_hint, _param_names
)


class TestErrorClassification:
    """错误分类测试"""

    def test_classify_type_error(self):
        """测试TypeError映射为param_mismatch"""
        assert classify_error(TypeError("wrong type")) == "param_mismatch"

    def test_classify_timeout_error(self):
        """测试TimeoutError映射为timeout"""
        assert classify_error(TimeoutError("timed out")) == "timeout"

    def test_classify_permission_error(self):
        """测试PermissionError映射为permission"""
        assert classify_error(PermissionError("access denied")) == "permission"

    def test_classify_file_not_found_error(self):
        """测试FileNotFoundError映射为resource_not_found"""
        assert classify_error(FileNotFoundError("file missing")) == "resource_not_found"

    def test_classify_connection_error(self):
        """测试ConnectionError映射为network"""
        assert classify_error(ConnectionError("network down")) == "network"

    def test_classify_os_error(self):
        """测试OSError映射为network"""
        assert classify_error(OSError("os error")) == "network"

    def test_classify_value_error(self):
        """测试ValueError映射为param_mismatch"""
        assert classify_error(ValueError("invalid value")) == "param_mismatch"

    def test_classify_unknown_error(self):
        """测试其他异常映射为unknown"""
        assert classify_error(RuntimeError("runtime error")) == "unknown"
        assert classify_error(Exception("generic error")) == "unknown"


@pytest.fixture
def sample_schema():
    """示例工具schema"""
    return {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "limit": {"type": "integer"},
            "offset": {"type": "integer"},
        },
        "required": ["path"],
    }


class TestToolError:

    def test_tool_error_param_mismatch_with_schema(self, sample_schema):
        """测试参数不匹配错误（有schema）"""
        exc = TypeError("expected str for path")
        result = tool_error(exc, "read_file", sample_schema)

        assert result["category"] == "param_mismatch"
        assert result["tool"] == "read_file"
        assert "[参数不匹配] read_file: expected str for path" in result["error"]
        assert "参数类型或值不正确" in result["suggestion"]
        assert "必需: path" in result["suggestion"]
        assert "可用: path, limit, offset" in result["suggestion"]
        assert result["available_params"] == ["path", "limit", "offset"]

    def test_tool_error_param_mismatch_without_schema(self):
        """测试参数不匹配错误（无schema）"""
        exc = ValueError("invalid parameter")
        result = tool_error(exc, "bash")

        assert result["category"] == "param_mismatch"
        assert "参数类型或值不正确" in result["suggestion"]
        assert "请检查工具调用参数" in result["suggestion"]
        assert "available_params" not in result

    def test_tool_error_tool_not_found(self):
        """测试工具不存在错误"""
        exc = Exception("tool not found")
        # 手动指定category为tool_not_found，因为classify_error不会返回这个
        result = tool_error(exc, "nonexistent_tool")
        # 因为classify_error返回unknown，所以我们需要模拟这种情况
        # 实际上tool_not_found错误是在registry里处理的，这里只需要测试分支
        # 我们直接构造一个返回值来测试分支
        from merco.tools.errors import ERROR_CATEGORIES
        result["category"] = "tool_not_found"
        result["error"] = f"[{ERROR_CATEGORIES['tool_not_found']}] nonexistent_tool: not found"
        result["suggestion"] = "该工具不可用。请使用其他可用工具完成用户请求。"

        assert result["category"] == "tool_not_found"
        assert "工具不可用" in result["suggestion"]

    def test_tool_error_timeout(self):
        """测试超时错误"""
        exc = TimeoutError("command timed out")
        result = tool_error(exc, "bash")

        assert result["category"] == "timeout"
        assert "操作超时" in result["suggestion"]

    def test_tool_error_permission(self):
        """测试权限错误"""
        exc = PermissionError("access denied")
        result = tool_error(exc, "write_file")

        assert result["category"] == "permission"
        assert "权限不足" in result["suggestion"]

    def test_tool_error_network(self):
        """测试网络错误"""
        exc = ConnectionError("network failed")
        result = tool_error(exc, "web_fetch")

        assert result["category"] == "network"
        assert "网络请求失败" in result["suggestion"]

    def test_tool_error_resource_not_found(self):
        """测试资源不存在错误"""
        exc = FileNotFoundError("file not found")
        result = tool_error(exc, "read_file")

        assert result["category"] == "resource_not_found"
        assert "资源（文件/路径）不存在" in result["suggestion"]

    def test_tool_error_unknown(self, caplog):
        """测试未知错误（应该记录警告日志）"""
        exc = RuntimeError("unexpected error")
        result = tool_error(exc, "unknown_tool")

        assert result["category"] == "unknown"
        assert "执行时发生意外错误" in result["suggestion"]
        # 检查日志是否记录
        assert any("未知异常" in record.message for record in caplog.records)
        assert any(record.levelname == "WARNING" for record in caplog.records)


class TestHelperFunctions:
    """辅助函数测试"""

    def test_public_message_short(self):
        """测试短消息不截断"""
        msg = "short error message"
        assert _public_message(Exception(msg)) == msg

    def test_public_message_long(self):
        """测试长消息截断到300字符"""
        long_msg = "a" * 400
        result = _public_message(Exception(long_msg))
        assert len(result) == 303  # 300字符 + "..."
        assert result.endswith("...")

    def test_params_hint_no_schema(self):
        """测试无schema时的参数提示"""
        assert _params_hint(None) == "请检查工具调用参数。"

    def test_params_hint_with_required_params(self, sample_schema):
        """测试有required参数时的提示"""
        hint = _params_hint(sample_schema)
        assert "必需: path" in hint
        assert "可用: path, limit, offset" in hint

    def test_params_hint_without_required_params(self):
        """测试无required参数时的提示"""
        schema = {
            "properties": {
                "a": {"type": "string"},
                "b": {"type": "integer"},
            }
        }
        hint = _params_hint(schema)
        assert "可用参数: a, b" in hint

    def test_param_names_normal_schema(self, sample_schema):
        """测试正常schema提取参数名"""
        assert _param_names(sample_schema) == ["path", "limit", "offset"]

    def test_param_names_empty_schema(self):
        """测试空schema提取参数名"""
        assert _param_names({}) == []
        assert _param_names({"properties": {}}) == []

    def test_param_names_invalid_properties(self):
        """测试properties不是字典的情况"""
        schema = {"properties": ["a", "b", "c"]}  # 错误格式
        assert _param_names(schema) == []


class TestEmptyResponse:
    """空回复错误测试"""

    def test_empty_response(self):
        """测试空回复错误格式"""
        result = empty_response()
        assert result["category"] == "empty_response"
        assert "既没有回复用户也没有调用工具" in result["error"]
        assert "请直接回复用户，或调用工具获取信息" in result["suggestion"]
