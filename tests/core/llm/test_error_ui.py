"""LLM 错误 UI 单元测试"""
from merco.core.llm.error_ui import (
    classify_error,
    sanitize_message,
    error_message,
    build_retry_line,
)


class TestErrorClassification:
    """错误分类测试"""

    def test_classify_401_unauthorized(self):
        """测试 401 认证错误"""
        exc = Exception("Unauthorized")
        exc.status_code = 401
        info = classify_error(exc)
        assert info.label == "认证失败"
        assert "API Key 无效或已过期" in info.hint

    def test_classify_401_from_message(self):
        """测试从错误消息识别认证错误"""
        exc = Exception("Invalid API key provided")
        info = classify_error(exc)
        assert info.label == "认证失败"

    def test_classify_403_forbidden(self):
        """测试 403 权限错误"""
        exc = Exception("Forbidden")
        exc.status_code = 403
        info = classify_error(exc)
        assert info.label == "权限不足"
        assert "账户无权限访问该资源" in info.hint

    def test_classify_404_model_not_found(self):
        """测试 404 模型不存在"""
        exc = Exception("Model gpt-5 not found")
        exc.status_code = 404
        info = classify_error(exc)
        assert info.label == "模型/接口不存在"
        assert "检查模型名和 base_url" in info.hint

    def test_classify_413_context_length(self):
        """测试 413 上下文过长"""
        exc = Exception("Context length exceeded")
        exc.status_code = 413
        info = classify_error(exc)
        assert info.label == "请求过长"
        assert "上下文超过模型上限" in info.hint

    def test_classify_context_length_from_message(self):
        """测试从错误消息识别上下文过长"""
        exc = Exception("prompt is too long for this model")
        info = classify_error(exc)
        assert info.label == "请求过长"

    def test_classify_429_rate_limit(self):
        """测试 429 限流错误"""
        exc = Exception("Too many requests")
        exc.status_code = 429
        info = classify_error(exc)
        assert info.label == "请求限流"
        assert "API 限流，稍后重试" in info.hint

    def test_classify_rate_limit_from_message(self):
        """测试从错误消息识别限流"""
        exc = Exception("Rate limit reached, please try again later")
        info = classify_error(exc)
        assert info.label == "请求限流"

    def test_classify_5xx_server_error(self):
        """测试 5xx 服务端错误"""
        exc = Exception("Internal Server Error")
        exc.status_code = 500
        info = classify_error(exc)
        assert info.label == "服务端错误 (500)"
        assert "API 服务器异常" in info.hint

    def test_classify_408_timeout(self):
        """测试 408 超时错误"""
        exc = Exception("Request Timeout")
        exc.status_code = 408
        info = classify_error(exc)
        assert info.label == "请求超时"
        assert "API 请求超时" in info.hint

    def test_classify_timeout_from_name(self):
        """测试从异常类名识别超时"""
        class TimeoutError(Exception):
            pass
        exc = TimeoutError("Request timed out")
        info = classify_error(exc)
        assert info.label == "请求超时"

    def test_classify_connection_error(self):
        """测试连接错误"""
        class ConnectionError(Exception):
            pass
        exc = ConnectionError("Failed to connect to API")
        info = classify_error(exc)
        assert info.label == "连接错误"
        assert "无法连接到 API 服务器" in info.hint

    def test_classify_other_4xx_error(self):
        """测试其他 4xx 错误"""
        exc = Exception("Bad Request")
        exc.status_code = 400
        info = classify_error(exc)
        assert info.label == "请求错误 (400)"
        assert "请求被服务端拒绝" in info.hint

    def test_classify_unknown_error(self):
        """测试未知错误"""
        exc = Exception("Something went wrong")
        info = classify_error(exc)
        assert info.label == "Exception"
        assert "API 调用失败" in info.hint


class TestMessageSanitization:
    """敏感信息脱敏测试"""

    def test_sanitize_api_key(self):
        """测试包含 api_key 的信息脱敏"""
        exc = Exception("Invalid api_key: sk-1234567890abcdef")
        sanitized = sanitize_message(exc)
        assert sanitized == "(包含敏感信息，已脱敏)"

    def test_sanitize_token(self):
        """测试包含 token 的信息脱敏"""
        exc = Exception("Token expired: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9")
        sanitized = sanitize_message(exc)
        assert sanitized == "(包含敏感信息，已脱敏)"

    def test_sanitize_secret(self):
        """测试包含 secret 的信息脱敏"""
        exc = Exception("Invalid secret: mysecret123")
        sanitized = sanitize_message(exc)
        assert sanitized == "(包含敏感信息，已脱敏)"

    def test_sanitize_authorization(self):
        """测试包含 authorization 的信息脱敏"""
        exc = Exception("Authorization header missing")
        sanitized = sanitize_message(exc)
        assert sanitized == "(包含敏感信息，已脱敏)"

    def test_sanitize_bearer(self):
        """测试包含 bearer 的信息脱敏"""
        exc = Exception("Bearer token invalid")
        sanitized = sanitize_message(exc)
        assert sanitized == "(包含敏感信息，已脱敏)"

    def test_sanitize_case_insensitive(self):
        """测试大小写不敏感"""
        exc = Exception("invalid API_KEY: sk-123")
        sanitized = sanitize_message(exc)
        assert sanitized == "(包含敏感信息，已脱敏)"

    def test_sanitize_api_key_with_space(self):
        """测试 'API key'（带空格）应被脱敏（回归测试 - Bug #3）"""
        exc = Exception("Invalid API key provided")
        sanitized = sanitize_message(exc)
        assert sanitized == "(包含敏感信息，已脱敏)"

    def test_sanitize_uppercase_api_key_with_space(self):
        """测试 'API KEY'（全大写+空格）应被脱敏"""
        exc = Exception("Failed with API KEY: sk-123")
        sanitized = sanitize_message(exc)
        assert sanitized == "(包含敏感信息，已脱敏)"

    def test_sanitize_compound_access_token(self):
        """测试复合词 'access_token' 应被脱敏"""
        exc = Exception("Error in access_token field")
        sanitized = sanitize_message(exc)
        assert sanitized == "(包含敏感信息，已脱敏)"

    def test_sanitize_compound_bearer_token(self):
        """测试 'Bearer token'（复合上下文）应被脱敏"""
        exc = Exception("Bearer token expired: abc123")
        sanitized = sanitize_message(exc)
        assert sanitized == "(包含敏感信息，已脱敏)"

    def test_sanitize_no_sensitive_info(self):
        """测试不包含敏感信息的正常消息"""
        exc = Exception("Model not found: gpt-5")
        sanitized = sanitize_message(exc)
        assert sanitized == "Model not found: gpt-5"

    def test_sanitize_long_message_truncated(self):
        """测试长消息截断"""
        long_msg = "x" * 400
        exc = Exception(long_msg)
        sanitized = sanitize_message(exc, max_len=300)
        assert len(sanitized) == 301  # 300 + '…'
        assert sanitized.endswith("…")

    def test_sanitize_exact_max_length(self):
        """测试刚好等于最大长度的消息不截断"""
        msg = "x" * 300
        exc = Exception(msg)
        sanitized = sanitize_message(exc, max_len=300)
        assert sanitized == msg
        assert not sanitized.endswith("…")


class TestErrorRendering:
    """错误信息渲染测试"""

    def test_error_message_format(self):
        """测试错误消息格式"""
        exc = Exception("Invalid API key")
        info = classify_error(exc)
        msg = error_message(info)
        assert msg.startswith("❌ [bold red]认证失败[/bold red]")
        assert "[red]API Key 无效或已过期" in msg
        # Bug #3 修复后：包含 "API key"（带空格）的错误消息也会被脱敏
        assert "(包含敏感信息，已脱敏)" in msg

    def test_build_retry_line(self):
        """测试重试行构建"""
        exc = Exception("Rate limit exceeded")
        info = classify_error(exc)
        line = build_retry_line(info, attempt=2, max_attempts=3, actions=["等待 3s", "压缩上下文"])
        assert "API 请求限流（第 2/3 次）" in line
        assert "等待 3s + 压缩上下文…" in line

    def test_build_retry_line_no_actions(self):
        """测试没有动作时的重试行"""
        exc = Exception("Rate limit exceeded")
        info = classify_error(exc)
        line = build_retry_line(info, attempt=1, max_attempts=3, actions=[])
        assert "立即重试" in line
