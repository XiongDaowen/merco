"""网络工具单元测试"""
from unittest.mock import AsyncMock, MagicMock, patch
import sys
import pytest
from merco.tools.web_tools import WebFetch, WebSearch


class TestWebFetch:
    """WebFetch 工具测试"""

    @pytest.fixture
    def fetch_tool(self):
        return WebFetch()

    @pytest.mark.asyncio
    async def test_fetch_html_format(self, fetch_tool):
        """测试获取HTML格式内容"""
        mock_response = AsyncMock()
        mock_response.text = "<html><body><h1>Hello</h1> World</body></html>"
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.get", return_value=mock_response):
            result = await fetch_tool.execute("https://example.com", format="html")

            assert "error" not in result
            assert result["url"] == "https://example.com"
            assert result["content"] == "<html><body><h1>Hello</h1> World</body></html>"

    @pytest.mark.asyncio
    async def test_fetch_text_format(self, fetch_tool):
        """测试获取纯文本格式内容（自动提取）"""
        mock_response = AsyncMock()
        mock_response.text = "<html><body><h1>Hello</h1>   World\n\nNew line</body></html>"
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.get", return_value=mock_response):
            result = await fetch_tool.execute("https://example.com", format="text")

            assert "error" not in result
            assert result["url"] == "https://example.com"
            # HTML标签被移除，多余空格被压缩
            assert result["content"] == "Hello World New line"

    @pytest.mark.asyncio
    async def test_fetch_http_error(self, fetch_tool):
        """测试HTTP错误处理"""
        mock_response = AsyncMock()
        mock_response.raise_for_status = MagicMock(side_effect=Exception("404 Not Found"))

        with patch("httpx.AsyncClient.get", return_value=mock_response):
            result = await fetch_tool.execute("https://example.com/nonexistent")

            assert "error" in result
            assert "404 Not Found" in result["error"]

    @pytest.mark.asyncio
    async def test_fetch_network_error(self, fetch_tool):
        """测试网络错误处理"""
        with patch("httpx.AsyncClient.get", side_effect=Exception("Network unreachable")):
            result = await fetch_tool.execute("https://example.com")

            assert "error" in result
            assert "Network unreachable" in result["error"]


class TestWebSearch:
    """WebSearch 工具测试"""

    @pytest.fixture
    def search_tool(self):
        return WebSearch()

    @pytest.mark.asyncio
    async def test_search_success(self, search_tool):
        """测试搜索成功返回结果"""
        mock_ddgs_instance = MagicMock()
        mock_ddgs_instance.text.return_value = [
            {"title": "Result 1", "href": "https://result1.com", "body": "Snippet 1"},
            {"title": "Result 2", "href": "https://result2.com", "body": "Snippet 2"},
        ]

        mock_ddgs = MagicMock()
        mock_ddgs.DDGS.return_value.__enter__.return_value = mock_ddgs_instance
        with patch.dict(sys.modules, {"ddgs": mock_ddgs}):
            result = await search_tool.execute("test query", n=2)

            assert "error" not in result
            assert result["query"] == "test query"
            assert len(result["results"]) == 2
            assert result["results"][0]["title"] == "Result 1"
            assert result["results"][0]["url"] == "https://result1.com"
            assert result["results"][0]["snippet"] == "Snippet 1"
            assert result["results"][1]["title"] == "Result 2"

    @pytest.mark.asyncio
    async def test_search_ddgs_not_installed(self, search_tool):
        """测试ddgs未安装的情况"""
        import builtins
        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "ddgs":
                raise ImportError("No module named 'ddgs'")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=mock_import):
            result = await search_tool.execute("test query")

            assert "error" in result
            assert "ddgs 未安装" in result["error"]
            assert result["results"] == []

    @pytest.mark.asyncio
    async def test_search_general_error(self, search_tool):
        """测试搜索过程中的一般错误"""
        mock_ddgs_instance = MagicMock()
        mock_ddgs_instance.text.side_effect = Exception("Search API error")

        mock_ddgs = MagicMock()
        mock_ddgs.DDGS.return_value.__enter__.return_value = mock_ddgs_instance
        with patch.dict(sys.modules, {"ddgs": mock_ddgs}):
            result = await search_tool.execute("test query")

            assert "error" in result
            assert "Search API error" in result["error"]
            assert result["results"] == []
