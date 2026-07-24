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
    """网络搜索 — DuckDuckGo (免费，无需 API key)"""

    name = "web_search"
    description = "搜索网络获取信息。返回标题、URL 和摘要。"
    toolset = "web"
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "搜索关键词"},
            "n": {"type": "integer", "description": "结果数量，默认 5"},
        },
        "required": ["query"],
    }

    async def execute(self, query: str, n: int = 5) -> dict:
        try:
            from ddgs import DDGS

            results = []
            with DDGS() as ddgs:
                for r in ddgs.text(query, max_results=n):
                    results.append(
                        {
                            "title": r["title"],
                            "url": r["href"],
                            "snippet": r["body"],
                        }
                    )
            return {"results": results, "query": query}
        except ImportError:
            return {"error": "ddgs 未安装。运行 pip install ddgs", "results": []}
        except Exception as e:
            return {"error": str(e), "results": []}
