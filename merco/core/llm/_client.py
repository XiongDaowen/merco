"""LLM 客户端 - OpenAI 兼容接口"""
import asyncio
import json
import logging
import re
import time
from typing import Any, Optional, AsyncIterator

from merco.core.llm.thinking import (
    THINK_TAG_PAIRS, _build_think_block_re, _THINK_BLOCK_RE,
    _strip_think_tags, _clean_content,
    ThinkingExtractor, ThinkingStrategy,
    DirectFieldStrategy, ModelExtraStrategy, ThinkTagStrategy,
)

logger = logging.getLogger("merco.llm")


# 清理字符串中的代理对字符（surrogates），防止 API 序列化崩溃
_SURROGATE_RE = re.compile(r'[\ud800-\udfff]')


def _clean_surrogates(obj):
    """递归清理数据结构中的代理对字符"""
    if isinstance(obj, str):
        return _SURROGATE_RE.sub('', obj)
    if isinstance(obj, list):
        return [_clean_surrogates(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _clean_surrogates(v) for k, v in obj.items()}
    return obj


def _extract_usage(response) -> dict:
    """从 API 响应中提取 token 用量，包括缓存命中"""
    usage = response.usage
    if not usage:
        return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    result = {
        "prompt_tokens": getattr(usage, "prompt_tokens", 0) or 0,
        "completion_tokens": getattr(usage, "completion_tokens", 0) or 0,
        "total_tokens": getattr(usage, "total_tokens", 0) or 0,
    }

    # 缓存命中 — 多 provider 兼容采集
    # Anthropic: usage.cache_read_input_tokens / cache_creation_input_tokens
    cached = getattr(usage, "cache_read_input_tokens", None)
    if cached is not None:
        result["cache_read_tokens"] = cached
        result["cache_write_tokens"] = getattr(usage, "cache_creation_input_tokens", 0) or 0

    # OpenAI: usage.prompt_tokens_details.cached_tokens
    details = getattr(usage, "prompt_tokens_details", None)
    if details is not None:
        cd = getattr(details, "cached_tokens", None)
        if cd is not None:
            result["cached_tokens"] = cd

    return result


class LLMClient:
    """OpenAI 兼容的 LLM 客户端 — 纯传输层，重试/恢复由 Agent RecoveryPipeline 统一处理"""

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4",
        base_url: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        cooldown: float = 0,  # 请求最小间隔（秒），0=不禁用
        extra_params: Optional[dict] = None,  # 额外 API 参数（top_p / seed 等）
        headers: Optional[dict] = None,  # 自定义 HTTP header（X-Title 等）
        stream_options: Optional[dict] = None,  # 流式额外参数（如 {"include_usage": True}）
    ):
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.cooldown = cooldown
        self.extra_params = extra_params or {}
        self.stream_options = stream_options
        self._last_request_time = 0.0
        self._client_ready = False

        import httpx
        from openai import AsyncOpenAI

        client_kwargs: dict = {
            "api_key": api_key,
            "max_retries": 0,
            "timeout": httpx.Timeout(connect=10.0, read=None, write=None, pool=10.0),
        }
        if base_url:
            client_kwargs["base_url"] = base_url
        if headers:
            client_kwargs["http_client"] = httpx.AsyncClient(headers=headers)

        self.client = AsyncOpenAI(**client_kwargs)

    # ── 公共方法 ─────────────────────────────────────────────────

    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] = None,
        tool_choice: str | dict[str, Any] = "auto",
    ) -> dict:
        """非流式聊天"""
        params = self._build_params(messages, tools, tool_choice)
        response = await self._request(params)
        result = self._parse_response(response)
        logger.debug("← API 响应: finish=%s content_len=%d tool_calls=%d",
                     result.get("finish_reason"), len(result.get("content", "")),
                     len(result.get("tool_calls", [])))
        return result

    async def chat_stream(
        self,
        messages: list[dict],
        tools: list[dict] = None,
        tool_choice: str | dict[str, Any] = "auto",
    ) -> AsyncIterator[dict]:
        """流式聊天"""
        extractor = ThinkingExtractor()
        params = self._build_params(messages, tools, tool_choice, stream=True)
        stream = await self._request(params)
        assert stream is not None
        async for chunk in stream:
            if parsed := self._parse_chunk(chunk, extractor):
                yield parsed

    # ── 私有方法 ─────────────────────────────────────────────────

    def _build_params(
        self, messages: list[dict], tools: list[dict] | None,
        tool_choice: str | dict[str, Any], stream: bool = False,
    ) -> dict:
        """构造 API 请求参数"""
        params = {
            "model": self.model,
            "messages": _clean_surrogates(messages),
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        if stream:
            params["stream"] = True
            options = {"include_usage": True}
            if self.stream_options:
                options.update(self.stream_options)
            params["stream_options"] = options
        if tools:
            params["tools"] = tools
            params["tool_choice"] = tool_choice
        params.update(self.extra_params)
        return params

    async def _ensure_client_ready(self):
        """确保 httpx 异步连接池初始化完成（首次请求前执行一次）。"""
        if self._client_ready:
            return
        await asyncio.sleep(0)
        self._client_ready = True

    async def _request(self, params: dict):
        """发送请求（含 cooldown），不重试。错误原样上抛交 Agent RecoveryPipeline。"""
        logger.debug("→ API 请求: model=%s messages=%d tools=%d",
                     self.model, len(params.get("messages", [])),
                     len(params.get("tools", [])))

        if self.cooldown > 0:
            elapsed = time.monotonic() - self._last_request_time
            if elapsed < self.cooldown:
                wait = self.cooldown - elapsed
                logger.debug("⏳ 冷却 %.1fs（距上次请求 %.1fs）", wait, elapsed)
                await asyncio.sleep(wait)

        try:
            await self._ensure_client_ready()
            response = await self.client.chat.completions.create(**params)
        except asyncio.CancelledError:
            logger.debug("⚠ 请求被取消")
            raise
        self._last_request_time = time.monotonic()
        return response

    @staticmethod
    def _normalize_tool_calls(tool_calls: list) -> list[dict]:
        """统一将 SDK tool_call 列表归一为安全 dict 列表，避免 None 穿透。"""
        result = []
        for tc in tool_calls:
            entry: dict = {
                "id": tc.id or "",
                "name": tc.function.name or "",
                "arguments": tc.function.arguments or "",
            }
            idx = getattr(tc, "index", None)
            if idx is not None:
                entry["index"] = idx
            result.append(entry)
        return result

    def _parse_response(self, response) -> dict:
        """解析完整响应"""
        if not response.choices:
            return {"content": "", "finish_reason": None, "usage": _extract_usage(response)}

        choice = response.choices[0]
        message = choice.message

        content = message.content or ""
        usage_data = _extract_usage(response)
        result = {
            "role": message.role,
            "content": content,
            "reasoning": "",
            "finish_reason": choice.finish_reason,
            "usage": usage_data,
        }

        extracted = ThinkingExtractor().extract_from_message(message)
        if extracted:
            if extracted.get("reasoning"):
                result["reasoning"] = extracted["reasoning"]
            if "content" in extracted:
                result["content"] = extracted["content"] if extracted["content"] else ""

        # 兜底：无论哪个策略命中，都清理 content 中残留的 <thinking> 标签
        # 防止 DirectFieldStrategy 命中后 ThinkTagStrategy 没跑导致标签泄漏
        result["content"] = _clean_content(result["content"])

        if message.tool_calls:
            normalized = self._normalize_tool_calls(message.tool_calls)
            logger.debug("_parse_response: 检测到 %d 个 tool_calls: %s",
                        len(normalized),
                        [f"{tc['name']}({tc['id'][:8]})" for tc in normalized])
            result["tool_calls"] = [
                {**tc, "arguments": json.loads(tc["arguments"]) if tc["arguments"] else {}}
                for tc in normalized
            ]

        return result

    def _parse_chunk(self, chunk, extractor: Optional["ThinkingExtractor"] = None) -> Optional[dict]:
        """解析流式块"""
        choice = chunk.choices[0] if chunk.choices else None
        if not choice:
            return None

        delta = choice.delta
        if delta is None:
            return None
        result = {}
        ex = extractor if extractor is not None else ThinkingExtractor()
        extracted = ex.extract_from_delta(delta)
        if extracted.get("content"):
            result["content"] = _strip_think_tags(extracted["content"])
        if extracted.get("reasoning"):
            result["reasoning"] = _strip_think_tags(extracted["reasoning"])
        if delta.tool_calls:
            result["tool_calls"] = self._normalize_tool_calls(delta.tool_calls)
            tcs = result["tool_calls"]
            logger.debug("_parse_chunk: 流式收到 %d 个 tool_calls delta: index=%s name=%s",
                        len(tcs),
                        [tc.get("index", "?") for tc in tcs],
                        [tc.get("name", "") or "?" for tc in tcs])

        if choice.finish_reason:
            result["finish_reason"] = choice.finish_reason
        if hasattr(chunk, "usage") and chunk.usage:
            result["usage"] = {
                "prompt_tokens": chunk.usage.prompt_tokens,
                "completion_tokens": chunk.usage.completion_tokens,
                "total_tokens": chunk.usage.total_tokens,
            }
        return result if result else None
