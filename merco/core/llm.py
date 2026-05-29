"""LLM 客户端 - OpenAI 兼容接口"""
import json
import logging
import re
import time
import asyncio
from abc import ABC, abstractmethod
from typing import Any, Optional, AsyncIterator

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


# ── Thinking 提取策略体系 ─────────────────────────────────────────

_THINK_TAG_RE = re.compile(r"</?(?:think|thinking)>", re.IGNORECASE)
_THINK_BLOCK_RE = re.compile(r"<think(?:ing)?>.*?</think(?:ing)?>", re.DOTALL | re.IGNORECASE)


def _strip_think_tags(text: str) -> str:
    """移除 content 中残留的 <thinking>...</thinking> 块及其标签"""
    return _THINK_BLOCK_RE.sub("", text).strip()


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


class ThinkingStrategy(ABC):
    """思考内容提取策略基类。子类注册到 ThinkingExtractor 后按优先级调用。"""

    @abstractmethod
    def extract_from_delta(self, delta: Any) -> dict | None:
        """从流式 delta 中提取。返回 {'content'?: str, 'reasoning'?: str} 或 None。"""
        ...

    @abstractmethod
    def extract_from_message(self, message: Any) -> dict | None:
        """从完整 message（非流式）中提取。"""
        ...

    def reset(self) -> None:
        """重置跨 chunk 状态。"""
        pass


class DirectFieldStrategy(ThinkingStrategy):
    """直接从对象属性检查 reasoning_content / reasoning（scnet 等代理放在顶层字段）。"""

    def extract_from_delta(self, delta: Any) -> dict | None:
        return self._check(delta)

    def extract_from_message(self, message: Any) -> dict | None:
        return self._check(message)

    @staticmethod
    def _check(obj: Any) -> dict | None:
        try:
            for attr in ("reasoning_content", "reasoning"):
                val = getattr(obj, attr, None)
                if val and isinstance(val, str):
                    return {"reasoning": val}
        except Exception:
            pass
        return None


class ModelExtraStrategy(ThinkingStrategy):
    """从 model_extra 提取 reasoning_content / reasoning（OpenAI o1 / DeepSeek R1 等）。"""

    def extract_from_delta(self, delta: Any) -> dict | None:
        return self._extract_from(delta)

    def extract_from_message(self, message: Any) -> dict | None:
        return self._extract_from(message)

    @staticmethod
    def _extract_from(obj: Any) -> dict | None:
        try:
            extra = getattr(obj, "model_extra", None)
            if isinstance(extra, dict):
                rc = extra.get("reasoning_content") or extra.get("reasoning") or ""
                if rc:
                    return {"reasoning": str(rc)}
        except Exception:
            pass
        return None


_THINK_TAGS = ("<think>", "</think>", "<thinking>", "</thinking>")


class ThinkTagStrategy(ThinkingStrategy):
    """从 <think>...</think> / <thinking>...</thinking> 标签中提取思考内容。
    流式场景用状态机处理标签跨 chunk 的情况。"""

    def __init__(self):
        self._in_thinking = False
        self._open_tag = ""
        self._close_tag = ""

    def reset(self) -> None:
        self._in_thinking = False
        self._open_tag = ""
        self._close_tag = ""

    def extract_from_delta(self, delta: Any) -> dict | None:
        content = getattr(delta, "content", None) or ""
        if not content:
            return None

        if self._in_thinking:
            if self._close_tag in content:
                before_close, after_close = content.split(self._close_tag, 1)
                self._in_thinking = False
                result: dict = {}
                if before_close:
                    result["reasoning"] = before_close
                result["content"] = after_close
                return result
            else:
                return {"reasoning": content, "content": ""}
        else:
            # 检测开标签（优先匹配较长的）
            for pair in (("<thinking>", "</thinking>"), ("<think>", "</think>")):
                ot, ct = pair
                if ot in content:
                    before_open, rest = content.split(ot, 1)
                    if ct in rest:
                        thinking, after_close = rest.split(ct, 1)
                        result: dict = {}
                        if thinking:
                            result["reasoning"] = thinking
                        cleaned = before_open + after_close
                        result["content"] = cleaned
                        return result
                    else:
                        self._in_thinking = True
                        self._open_tag = ot
                        self._close_tag = ct
                        result: dict = {"reasoning": rest, "content": before_open}
                        return result
            return {"content": content}

    def extract_from_message(self, message: Any) -> dict | None:
        """非流式：完整 content 一次性提取所有 think/thinking 标签。"""
        content = getattr(message, "content", None) or ""
        for tag in ("<thinking>", "<think>"):
            if tag in content:
                close_tag = tag.replace("<", "</")
                pattern = re.compile(re.escape(tag) + r"(.*?)" + re.escape(close_tag), re.DOTALL)
                cleaned = pattern.sub("", content).strip()
                thinking_parts = pattern.findall(content)
                thinking = "\n\n".join(t.strip() for t in thinking_parts)
                result: dict = {"reasoning": thinking}
                if cleaned:
                    result["content"] = cleaned
                return result
        return None


class ThinkingExtractor:
    """策略链式思考提取器。按注册顺序尝试各策略，
    首个返回非空 reasoning 的结果生效。"""

    def __init__(self):
        self._strategies: list[ThinkingStrategy] = [
            DirectFieldStrategy(),
            ModelExtraStrategy(),
            ThinkTagStrategy(),
        ]

    def register(self, strategy: ThinkingStrategy) -> None:
        """扩展点：注册新策略，插到链首。"""
        self._strategies.insert(0, strategy)

    def extract_from_delta(self, delta: Any) -> dict:
        """流式块提取，返回 dict 可能含 content / reasoning。"""
        for s in self._strategies:
            result = s.extract_from_delta(delta)
            if result is not None:
                if "content" not in result:
                    raw = getattr(delta, "content", None) or ""
                    result["content"] = raw
                return result
        raw = getattr(delta, "content", None) or ""
        return {"content": raw}

    def extract_from_message(self, message: Any) -> dict:
        """非流式响应提取。"""
        for s in self._strategies:
            result = s.extract_from_message(message)
            if result is not None:
                return result
        return {}

    def reset(self) -> None:
        for s in self._strategies:
            s.reset()


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
    ):
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.cooldown = cooldown
        self._last_request_time = 0.0

        import httpx
        from openai import AsyncOpenAI

        client_kwargs = {
            "api_key": api_key,
            "max_retries": 0,
            "timeout": httpx.Timeout(connect=10.0, read=None, write=None, pool=10.0),
        }
        if base_url:
            client_kwargs["base_url"] = base_url

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
        if tools:
            params["tools"] = tools
            params["tool_choice"] = tool_choice
        return params

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

        response = await self.client.chat.completions.create(**params)
        self._last_request_time = time.monotonic()
        return response

    def _parse_response(self, response) -> dict:
        """解析完整响应"""
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
        result["content"] = _strip_think_tags(result["content"])

        if message.tool_calls:
            result["tool_calls"] = [
                {
                    "id": tc.id,
                    "name": tc.function.name,
                    "arguments": json.loads(tc.function.arguments),
                }
                for tc in message.tool_calls
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
            result["content"] = extracted["content"]
        if extracted.get("reasoning"):
            result["reasoning"] = extracted["reasoning"]
        if delta.tool_calls:
            result["tool_calls"] = [
                {
                    "index": tc.index,
                    "id": tc.id,
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                }
                for tc in delta.tool_calls
            ]

        if choice.finish_reason:
            result["finish_reason"] = choice.finish_reason
        if hasattr(chunk, "usage") and chunk.usage:
            result["usage"] = {
                "prompt_tokens": chunk.usage.prompt_tokens,
                "completion_tokens": chunk.usage.completion_tokens,
                "total_tokens": chunk.usage.total_tokens,
            }
        return result if result else None
