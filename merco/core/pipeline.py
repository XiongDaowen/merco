"""结果处理管道 — 链式变换工具结果的可扩展中间层

设计原则：
- 每个 Processor 只做一件事，通过 use() 组合
- 管线顺序即执行顺序，先注册的先执行
- Processor 返回 True = 停止管线，后续不执行
- context.side_effects 存储需额外注入的消息（如 skill 内容作为 user message）
- 零动态开销：简单列表遍历，无反射/装饰器
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from merco.core.config import ModelConfig

logger = logging.getLogger("merco.pipeline")

# ── 上下文 ───────────────────────────────────────────────

@dataclass
class ProcessContext:
    """管线上下文，在处理器链之间传递和变换"""

    tool_name: str
    arguments: dict
    result: dict                       # 当前结果，处理器可原地修改
    tool_schema: dict | None = None
    tool_call_id: str = ""
    # 额外要添加到上下文的 side-effect 消息（如 skill 内容注入）
    extra_messages: list[dict] = field(default_factory=list)
    # 处理器间共享的临时数据
    metadata: dict = field(default_factory=dict)


# ── 处理器 ───────────────────────────────────────────────

class Processor(ABC):
    """处理器基类。每个处理器只做一件事。"""

    name: str = ""

    @abstractmethod
    async def process(self, ctx: ProcessContext) -> bool:
        """处理结果。返回 True 以停止管线（后续处理器跳过）。"""
        ...


# ── 管线 ─────────────────────────────────────────────────

class ResultPipeline:
    """结果处理管线。用 use() 注册处理器，process() 链式执行。"""

    def __init__(self):
        self._processors: list[Processor] = []
        self._by_name: dict[str, Processor] = {}
        self._disabled: set[str] = set()

    def use(self, processor: Processor) -> "ResultPipeline":
        """注册处理器。按注册顺序执行。"""
        self._processors.append(processor)
        self._by_name[processor.name] = processor
        return self

    def disable(self, name: str) -> None:
        """临时禁用指定处理器"""
        self._disabled.add(name)

    def enable(self, name: str) -> None:
        """重新启用指定处理器"""
        self._disabled.discard(name)

    async def process(self, ctx: ProcessContext) -> None:
        """链式执行所有启用的处理器"""
        for p in self._processors:
            if p.name in self._disabled:
                continue
            try:
                stop = await p.process(ctx)
                if stop:
                    break
            except Exception:
                logger.warning("管线处理器 '%s' 异常", p.name, exc_info=True)



def _walk_truncate(obj, max_per_value: int, filepath: str, pagination: dict | None = None):
    """递归截断字典/列表中所有超长字符串，附加分页信息。

    兼容所有工具返回格式——bash.stdout、read_file.content、web_fetch.content 等。
    非字符串值原样保留，嵌套结构递归处理。
    """
    if isinstance(obj, str):
        if len(obj) <= max_per_value:
            return obj
        preview = obj[:max_per_value]
        page_info = ""
        if pagination:
            # 用 offset/limit 翻页（不再用已删除的 char_offset/char_limit）
            # page_size 是字符数，按 ~60 字符/行估算行数
            lines_per_page = max(1, pagination["page_size"] // 60)
            next_offset = lines_per_page + 1
            page_info = (
                f"\n📄 第 1/{pagination['total_pages']} 页"
                f"（共 {pagination['total_chars']:,} 字符）\n"
                f"➡️ 下一页: read_file {filepath} offset={next_offset} limit={lines_per_page}"
            )
        return f"{preview}\n\n⚠️ 已截断{page_info}"
    if isinstance(obj, dict):
        return {k: _walk_truncate(v, max_per_value, filepath, pagination) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_walk_truncate(v, max_per_value, filepath, pagination) for v in obj]
    return obj


def _is_reading_trunc_file(ctx: ProcessContext, trunc_dir: str) -> bool:
    """检测是否正在读取截断缓存文件（防套娃）。"""
    # read_file(path=...) / write_file(path=...) 等文件工具的 path 参数
    path_arg = ctx.arguments.get("path", "")
    if isinstance(path_arg, str) and path_arg.startswith(trunc_dir):
        return True
    # bash 中也可能 cat/grep 截断文件，但结果通常不超限 → 低风险
    # 未来可扩展其他工具
    return False



# ── LLM 调用恢复管线 ──────────────────────────────────────

@dataclass
class RecoveryContext:
    """恢复管线上下文——策略的「诊断面板」。

    调用方（Agent）填入诊断信息，策略根据这些信息表达恢复意图。
    策略只设置标志位，不执行——由 Agent 在管线返回后统一执行。
    """

    # ── 诊断（Agent 填入）────────────────
    error: Exception
    status_code: int = 0                  # HTTP 状态码（ProviderError 自动提取）
    context_tokens: int = 0               # 当前上下文 token 估算
    tool_count: int = 0                   # 请求中的工具数量
    attempt_count: int = 0                # 本轮已尝试恢复次数（跨策略累计）
    model: str = ""                       # 当前模型名

    # ── 意图标志位（策略设置，Agent 执行）──
    compress: bool = False                # 需要压缩上下文
    reduce_tools: bool = False            # 需要精简工具列表
    switch_model: ModelConfig | None = None   # 跨 provider 切换（provider+model 全 spec）
    reduce_history: bool = False          # 需要裁剪对话历史
    extra_wait: float = 0.0               # 额外等待时间（秒），0 = 不等

    # ── 限制 ────────────────────────────
    compress_count: int = 0               # 已执行压缩的次数
    max_compress: int = 2                 # 允许的最大压缩次数
    max_reduce: int = 1                   # 允许的最大精简次数


class Recovery:
    """LLM 调用失败时的恢复策略基类。

    子类读取 RecoveryContext 的诊断字段做决策，设置标志位表达意图。
    返回 True = 已决策恢复，Agent 执行标志位后重试；False = 无法处理。

    框架预留的动态能力（当前未实现，标志位已就绪）:
    - reduce_tools:  上下文过大时自动精简工具（如关闭 idle/5xx 的工具集）
    - switch_model:  当前模型不可用时降级到备选模型
    - reduce_history: 裁剪遥远的对话轮次
    """

    name: str = ""

    @abstractmethod
    async def attempt(self, ctx: RecoveryContext) -> bool:
        """根据 ctx 诊断信息做决策，设置标志位。"""
        ...


class RecoveryPipeline:
    """LLM 调用恢复管线。按注册顺序尝试，第一个成功的策略生效。"""

    def __init__(self):
        self._recoveries: list[Recovery] = []
        self._disabled: set[str] = set()

    def use(self, recovery: Recovery) -> "RecoveryPipeline":
        self._recoveries.append(recovery)
        return self

    def disable(self, name: str) -> None:
        self._disabled.add(name)

    def enable(self, name: str) -> None:
        self._disabled.discard(name)

    async def attempt(self, ctx: RecoveryContext) -> bool:
        """依次尝试恢复策略，任一成功即返回 True"""
        for r in self._recoveries:
            if r.name in self._disabled:
                continue
            try:
                if await r.attempt(ctx):
                    ctx.attempt_count += 1
                    if ctx.compress:
                        ctx.compress_count += 1
                    return True
            except Exception:
                logger.warning("恢复策略 '%s' 异常", r.name, exc_info=True)
        return False


# ── 空回复处理管线 ─────────────────────────────────────────

@dataclass
class EmptyResponseContext:
    """空回复处理的上下文。管线策略读取诊断字段，设置标志位。"""

    reasoning: str = ""           # 模型输出的 reasoning 内容
    retry_count: int = 0          # 本轮已重试次数
    max_retries: int = 2          # 允许的最大重试次数

    # ── 意图标志位 ────────────────
    inject_error: str | None = None  # 要注入上下文的 user 错误消息


class EmptyResponseStrategy(ABC):
    """空回复策略：第一个 enabled 的策略生效。"""

    name: str = ""

    @abstractmethod
    async def attempt(self, ctx: EmptyResponseContext) -> bool:
        """返回 True = 已处理，Agent 执行标志位后重试；False = 放过"""
        ...


class EmptyResponsePipeline:
    """空回复处理管线。按注册顺序尝试，第一个成功的策略生效。"""

    def __init__(self):
        self._strategies: list[EmptyResponseStrategy] = []
        self._disabled: set[str] = set()

    def use(self, strategy: EmptyResponseStrategy) -> "EmptyResponsePipeline":
        self._strategies.append(strategy)
        return self

    def disable(self, name: str) -> None:
        self._disabled.add(name)

    def enable(self, name: str) -> None:
        self._disabled.discard(name)

    async def attempt(self, ctx: EmptyResponseContext) -> bool:
        for s in self._strategies:
            if s.name in self._disabled:
                continue
            try:
                if await s.attempt(ctx):
                    return True
            except Exception:
                logger.warning("空回复策略 '%s' 异常", s.name, exc_info=True)
        return False
