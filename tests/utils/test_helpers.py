"""工具辅助函数单元测试"""

from pathlib import Path

from merco.utils.helpers import expand_path, extract_urls, format_bytes, slugify, truncate


class TestExpandPath:
    """expand_path 测试"""

    def test_expand_user_home(self, monkeypatch, tmp_path):
        """测试展开用户主目录"""
        # 创建临时 HOME 目录
        monkeypatch.setenv("HOME", str(tmp_path))
        result = expand_path("~/test.txt")
        assert result == tmp_path / "test.txt"

    def test_expand_env_var(self, monkeypatch):
        """测试展开环境变量"""
        monkeypatch.setenv("TEST_DIR", "/tmp/test")
        result = expand_path("$TEST_DIR/file.txt")
        assert result == Path("/tmp/test/file.txt")

    def test_expand_absolute_path(self):
        """测试绝对路径不变"""
        result = expand_path("/etc/passwd")
        assert result == Path("/etc/passwd")

    def test_expand_relative_path(self, tmp_path, monkeypatch):
        """测试相对路径保持相对（Path() 不会自动展开为绝对路径）"""
        # Path("file.txt") 是相对路径，不会基于 HOME
        result = expand_path("file.txt")
        assert result == Path("file.txt")


class TestTruncate:
    """truncate 测试"""

    def test_no_truncate_when_short(self):
        """测试短文本不被截断"""
        result = truncate("hello", max_length=10)
        assert result == "hello"

    def test_exact_length_no_truncate(self):
        """测试刚好等于最大长度不被截断"""
        result = truncate("hello", max_length=5)
        assert result == "hello"

    def test_truncate_long_text(self):
        """测试长文本被截断"""
        result = truncate("a" * 100, max_length=10)
        assert len(result) == 10
        assert result.endswith("...")
        assert result == "aaaaaaa..."

    def test_custom_suffix(self):
        """测试自定义后缀"""
        result = truncate("a" * 100, max_length=10, suffix="…")
        assert result.endswith("…")
        assert len(result) == 10

    def test_empty_string(self):
        """测试空字符串"""
        result = truncate("", max_length=10)
        assert result == ""


class TestExtractUrls:
    """extract_urls 测试"""

    def test_extract_http_urls(self):
        """测试提取 http URL"""
        text = "Check out https://example.com for more info"
        urls = extract_urls(text)
        assert "https://example.com" in urls

    def test_extract_https_urls(self):
        """测试提取 https URL"""
        text = "Visit https://github.com/user/repo"
        urls = extract_urls(text)
        assert "https://github.com/user/repo" in urls

    def test_extract_www_urls(self):
        """测试提取 www URL"""
        text = "Go to www.example.com"
        urls = extract_urls(text)
        assert "www.example.com" in urls

    def test_extract_multiple_urls(self):
        """测试提取多个 URL"""
        text = "Visit https://example.com and www.github.com today"
        urls = extract_urls(text)
        assert len(urls) == 2
        assert "https://example.com" in urls
        assert "www.github.com" in urls

    def test_no_urls(self):
        """测试没有 URL 的文本"""
        text = "Just plain text without links"
        urls = extract_urls(text)
        assert urls == []


class TestSlugify:
    """slugify 测试"""

    def test_lowercase_and_strip(self):
        """测试转小写和去前后空白"""
        assert slugify("  HELLO World  ") == "hello-world"

    def test_replace_spaces(self):
        """测试空格替换为连字符"""
        assert slugify("hello world") == "hello-world"

    def test_replace_underscores(self):
        """测试下划线替换为连字符"""
        assert slugify("hello_world") == "hello-world"

    def test_replace_special_chars(self):
        """测试移除特殊字符"""
        assert slugify("hello, world!") == "hello-world"

    def test_multiple_separators(self):
        """测试多个连续分隔符合并"""
        assert slugify("hello___world") == "hello-world"
        assert slugify("hello---world") == "hello-world"
        assert slugify("hello _- world") == "hello-world"

    def test_strip_leading_trailing_hyphens(self):
        """测试去除首尾连字符"""
        assert slugify("---hello world---") == "hello-world"

    def test_chinese_preserved(self):
        """测试中文字符保留"""
        result = slugify("Hello 世界")
        assert "hello" in result
        assert "世界" in result


class TestFormatBytes:
    """format_bytes 测试"""

    def test_bytes(self):
        """测试字节单位"""
        assert format_bytes(512) == "512.0 B"

    def test_kilobytes(self):
        """测试 KB 单位"""
        assert format_bytes(1024) == "1.0 KB"
        assert format_bytes(2048) == "2.0 KB"

    def test_megabytes(self):
        """测试 MB 单位"""
        assert format_bytes(1024 * 1024) == "1.0 MB"

    def test_gigabytes(self):
        """测试 GB 单位"""
        assert format_bytes(1024**3) == "1.0 GB"

    def test_terabytes(self):
        """测试 TB 单位"""
        assert format_bytes(1024**4) == "1.0 TB"

    def test_zero_bytes(self):
        """测试零字节"""
        assert format_bytes(0) == "0.0 B"
