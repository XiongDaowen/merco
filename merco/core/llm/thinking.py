"""Thinking 提取策略体系 — 从模型输出中分离思考内容（reasoning）与正文"""
import re
from abc import ABC, abstractmethod
from typing import Any


# ── Thinking 提取策略体系 ─────────────────────────────────────────

# 统一的 think 标签对配置（开标签 → 闭标签）
# 新增 provider 只需在此添加一对标签
THINK_TAG_PAIRS: tuple[tuple[str, str], ...] = (
    ("<think>", "[/think]"),      # MiniMax 等
    ("<think>", "</think>"),       # 标准格式
    ("<thinking>", "</thinking>"), # XML 格式
)


def _build_think_block_re() -> re.Pattern:
    """根据 THINK_TAG_PAIRS 构建匹配所有 think 块的正则。

    构造策略：
      1. 收集所有模式（块 + 单标签）
      2. 按"长度降序"排序——块（长）必须先于裸标签（短）
      3. 用非捕获组组装，避免 sub() 因空捕获组错位

    排序是关键：Python re 交替是"左优先"，短模式排在前面会"吞掉"块首字符，
    导致长块模式失配。例如块模式 <think>...[/think] 在前时，遇到 <think>hi</think>
    会先匹配 <think> 裸标签，块模式再也匹配不上。
    """
    raw_patterns = []
    for open_tag, close_tag in THINK_TAG_PAIRS:
        eo = re.escape(open_tag)
        ec = re.escape(close_tag)
        raw_patterns.append(f"{eo}.*?{ec}")  # 完整块
        raw_patterns.append(eo)              # 孤儿开标签
        raw_patterns.append(ec)              # 孤儿闭标签
    # 长度降序：块（最长）必须先于单标签
    raw_patterns.sort(key=len, reverse=True)
    return re.compile("|".join(f"(?:{p})" for p in raw_patterns), re.IGNORECASE | re.DOTALL)


_THINK_BLOCK_RE = _build_think_block_re()


def _strip_think_tags(text: str) -> str:
    """chunk 安全：只去 think 标签，不动空白。
    流式场景专用——每 chunk 调一次，.strip() 会破坏词边界。"""
    return _THINK_BLOCK_RE.sub("", text)


def _clean_content(text: str) -> str:
    """完整 content 终态处理：去 think 标签 + 去前后空白。
    非流式专用——完整响应只需调一次，strip 收尾合理。"""
    return _THINK_BLOCK_RE.sub("", text).strip()


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


class ThinkTagStrategy(ThinkingStrategy):
    """从 think 标签中提取思考内容。

    使用统一的 THINK_TAG_PAIRS 配置，流式场景用状态机处理标签跨 chunk 的情况。
    新增标签格式只需修改 THINK_TAG_PAIRS。
    """

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
            # 继续处理跨 chunk 的 think 块
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
            # 检测开标签（使用 THINK_TAG_PAIRS，优先匹配较长的）
            for ot, ct in THINK_TAG_PAIRS:
                if ot in content:
                    before_open, rest = content.split(ot, 1)
                    if ct in rest:
                        thinking, after_close = rest.split(ct, 1)
                        result: dict = {}
                        if thinking:
                            result["reasoning"] = thinking
                        result["content"] = before_open + after_close
                        return result
                    # 开标签命中但闭标签不匹配：尝试下一个标签对
                    # （THINK_TAG_PAIRS 中可能有同开标签+不同闭标签，
                    # 例如 ("<think>", "[/think]") 与 ("<think>", "</think>")）
                    # 如果所有标签对都不匹配，再走跨 chunk 分支
            # 全部标签对都不匹配：进入跨 chunk 状态机，等待闭标签
            for ot, ct in THINK_TAG_PAIRS:
                if ot in content:
                    before_open, rest = content.split(ot, 1)
                    self._in_thinking = True
                    self._open_tag = ot
                    self._close_tag = ct
                    result: dict = {"reasoning": rest, "content": before_open}
                    return result
            return {"content": content}

    def extract_from_message(self, message: Any) -> dict | None:
        """非流式：完整 content 一次性提取所有 think 块。"""
        content = getattr(message, "content", None) or ""
        for open_tag, close_tag in THINK_TAG_PAIRS:
            if open_tag in content:
                pattern = re.compile(
                    re.escape(open_tag) + r"(.*?)" + re.escape(close_tag),
                    re.DOTALL
                )
                thinking_parts = pattern.findall(content)
                if thinking_parts:
                    cleaned = pattern.sub("", content).strip()
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
                    result["content"] = _strip_think_tags(raw)
                return result
        raw = getattr(delta, "content", None) or ""
        return {"content": _strip_think_tags(raw)}

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


def make_thinking_extractor(model: str) -> "ThinkingExtractor":
    """Pick a ThinkingExtractor strategy chain for the model name."""
    ex = ThinkingExtractor()
    model_lower = (model or "").lower()
    # ThinkTagStrategy is always in the default chain; the factory is a seam
    # for future per-model tuning. DeepSeek-reasoner emits <think> tags.
    if "deepseek" in model_lower:
        # ensure ThinkTagStrategy is present (it is, by default)
        return ex
    return ex
