"""网络工具 - 搜索与抓取"""

import httpx
from .base import BaseTool


class WebFetch(BaseTool):
    """抓取网页内容"""

    name = "web_fetch"
    description = "获取指定 URL 的内容"
    toolset = "web"
    parameters = {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "目标 URL"},
            "format": {"type": "string", "enum": ["text", "html"], "description": "返回格式"},
        },
        "required": ["url"],
    }

    async def execute(self, url: str, format: str = "text") -> dict:
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, follow_redirects=True, timeout=30)
                response.raise_for_status()

                if format == "html":
                    return {"content": response.text, "url": url}
                else:
                    # 简单提取文本内容
                    import re
                    text = re.sub(r"<[^>]+>", "", response.text)
                    text = re.sub(r"\s+", " ", text).strip()
                    return {"content": text, "url": url}

        except Exception as e:
            return {"error": str(e)}


class WebSearch(BaseTool):
    """网络搜索"""

    name = "web_search"
    description = "搜索网络获取信息"
    toolset = "web"
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "搜索关键词"},
            "num_results": {"type": "integer", "description": "结果数量"},
        },
        "required": ["query"],
    }

    def check(self) -> bool:
        """搜索 API 未配置时隐藏此工具"""
        return False  # TODO: 接入搜索 API 后改为 True

    async def execute(self, query: str, num_results: int = 5) -> dict:
        # TODO: 集成实际搜索 API（如 Firecrawl、SearXNG 等）
        return {"results": [], "note": "Web search not yet configured"}


from .registry import tool_registry  # noqa: E402 — 模块末尾自注册
tool_registry.register(WebFetch())
tool_registry.register(WebSearch())
