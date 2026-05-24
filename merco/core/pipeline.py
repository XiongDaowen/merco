"""结果处理管道 — 链式变换工具结果的可扩展中间层

设计原则：
- 每个 Processor 只做一件事，通过 use() 组合
- 管线顺序即执行顺序，先注册的先执行
- Processor 返回 True = 停止管线，后续不执行
- context.side_effects 存储需额外注入的消息（如 skill 内容作为 user message）
- 零动态开销：简单列表遍历，无反射/装饰器
"""

from __future__ import annotations

import asyncio
import json
import os
import time
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path

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


# ── 内置处理器 ─────────────────────────────────────────────

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
            page_info = (
                f"\n📄 第 1/{pagination['total_pages']} 页"
                f"（共 {pagination['total_chars']:,} 字符，每页 ~{pagination['page_size']:,} 字符）\n"
                f"➡️ 下一页: read_file {filepath} char_offset={pagination['page_size']} char_limit={pagination['page_size']}"
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


class TruncationProcessor(Processor):
    """通用结果截断：任意工具结果 → 写入完整 JSON 文件 → 返回递归截断版。

    对标 OpenCode truncate.ts 的缓存策略：

    - **触发条件**：整个 result dict 序列化为 JSON，超过 max_bytes 则截断
    - **缓存位置**：~/.merco/trunc/
    - **文件命名**：{timestamp_ms}_{safe_tool_name}.json（毫秒时间戳防冲突）
    - **缓存格式**：完整 JSON（保留所有字段结构）
    - **文件上限**：单文件最大 max_file_bytes（默认 50 MB），超限拒绝
    - **清理策略**：7 天过期自动删除（OpenCode 同款）
    - **清理频率**：懒清理 — 每次新写入时检查，距上次清理 > 1 小时才执行
    - **可配置**::

        pipeline.disable("truncation")                   # 调试时关闭
        TruncationProcessor(max_bytes=8000)              # 调大上下文窗口
        TruncationProcessor(retention_days=3)            # 加快清理
    """

    name = "truncation"
    _last_cleanup = 0.0          # 上次清理时间戳（类级，所有实例共享）
    _cleanup_interval = 3600     # 清理间隔（秒），1 小时

    def __init__(self, max_bytes: int = 4000, *,
                 retention_days: int = 7,
                 max_file_bytes: int = 50 * 1024 * 1024,
                 trunc_dir: str | None = None):
        self.max_bytes = max_bytes
        self.retention_days = retention_days
        self.max_file_bytes = max_file_bytes
        self._trunc_dir = trunc_dir

    @property
    def trunc_dir(self) -> str:
        if self._trunc_dir is None:
            self._trunc_dir = os.path.expanduser("~/.merco/trunc")
        return self._trunc_dir

    async def process(self, ctx: ProcessContext) -> bool:
        # 序列化整个结果判断是否需截断
        try:
            serialized = json.dumps(ctx.result, ensure_ascii=False)
        except (TypeError, ValueError):
            return False

        if len(serialized) <= self.max_bytes:
            return False

        reading_trunc_file = _is_reading_trunc_file(ctx, self.trunc_dir)
        per_value = max(int(self.max_bytes * 0.5), 500)
        total_chars = len(serialized)
        total_pages = (total_chars + per_value - 1) // per_value

        # 文件大小安全上限（超限不写文件）
        if total_chars > self.max_file_bytes:
            ctx.result["_truncated"] = True
            ctx.result["_pagination"] = {
                "total_chars": total_chars,
                "page_size": per_value,
                "total_pages": total_pages,
                "current_page": 1,
                "next_page_offset": per_value,
            }
            ctx.result["_hint"] = (
                f"结果过长（{total_chars:,} 字符，超过缓存上限 {self.max_file_bytes:,}），"
                f"已截断且未缓存至本地。可缩小请求范围重新执行。"
            )
            ctx.result = _walk_truncate(ctx.result, per_value, "[超出缓存上限，未保存]")
            return False

        # 分页元数据
        pagination = {
            "total_chars": total_chars,
            "page_size": per_value,
            "total_pages": total_pages,
            "current_page": 1,
            "next_page_offset": per_value,
        }

        if reading_trunc_file:
            # 防套娃：读截断缓存文件 → 截断内容但不写新文件
            ctx.result["_truncated"] = True
            ctx.result["_pagination"] = pagination
            ctx.result["_hint"] = (
                f"结果过长（{total_chars:,} 字符，第 1/{total_pages} 页）。"
                f"这是截断缓存文件，请用 read_file 的 offset/limit 翻页，"
                f"或用 bash grep 搜索关键信息。"
            )
            ctx.result = _walk_truncate(ctx.result, per_value,
                                        "[截断缓存文件]", pagination)
            return False

        # 正常截断：写缓存文件 + 分页
        os.makedirs(self.trunc_dir, exist_ok=True)
        self._maybe_cleanup()

        ts = int(time.time() * 1000)
        safe_name = ctx.tool_name.replace("/", "_")
        filepath = os.path.join(self.trunc_dir, f"{ts}_{safe_name}.json")
        try:
            Path(filepath).write_text(serialized, encoding="utf-8")
        except OSError:
            logger.warning("截断文件写入失败: %s", filepath)
            return False

        ctx.result["_truncated"] = True
        ctx.result["_full_output_path"] = filepath
        ctx.result["_pagination"] = pagination
        ctx.result["_hint"] = (
            f"结果过长（{total_chars:,} 字符，共 {total_pages} 页，每页 ~{per_value:,} 字符）。"
            f"当前第 1 页。"
            f"➡️ 下一页: read_file {filepath} char_offset={per_value} char_limit={per_value}"
            f" 或 bash grep 搜索关键信息。"
        )
        ctx.result = _walk_truncate(ctx.result, per_value, filepath, pagination)

        return False

    def _maybe_cleanup(self) -> None:
        """懒清理：距上次清理超过间隔才执行，删除超过 retention_days 的文件。"""
        now = time.time()
        if now - TruncationProcessor._last_cleanup < TruncationProcessor._cleanup_interval:
            return

        TruncationProcessor._last_cleanup = now
        cutoff = now - self.retention_days * 86400  # 秒
        removed = 0

        try:
            for entry in Path(self.trunc_dir).iterdir():
                if not entry.is_file():
                    continue
                if not entry.name.endswith(".json"):
                    continue
                try:
                    if entry.stat().st_mtime < cutoff:
                        entry.unlink()
                        removed += 1
                except OSError:
                    pass
        except OSError:
            pass  # 目录不存在等

        if removed:
            logger.info("截断缓存清理: 删除 %d 个过期文件 (> %d 天)", removed, self.retention_days)


class SkillViewProcessor(Processor):
    """Skill 注入：skill_view 结果以 user message 注入上下文。

    对标 Hermes：skill 内容以 role=user 注入（高优先级 + prompt cache 友好）。
    不追加到 system prompt（跨 provider 兼容更好）。
    """

    name = "skill_view"

    async def process(self, ctx: ProcessContext) -> bool:
        if ctx.tool_name != "skill_view":
            return False
        if "error" in ctx.result:
            return False
        if "content" not in ctx.result:
            return False

        skill_name = ctx.result.get("name", "unknown")
        skill_content = ctx.result["content"]
        content_len = len(skill_content)

        # 工具结果只留占位信息
        ctx.result["content"] = (
            f"技能 {skill_name} 已加载（{content_len:,} 字符），详见上下文。"
        )

        # 完整内容以 user message 注入
        user_msg = (
            f"技能 **{skill_name}** 已加载，请遵循以下指引：\n\n"
            f"{skill_content}"
        )
        # 仍然截断保护：user message 上限 8000
        if len(user_msg) > 8000:
            user_msg = user_msg[:7800] + "\n\n...(技能内容过长，已截断)"

        ctx.extra_messages.append({
            "role": "user",
            "content": user_msg,
        })

        return False  # 不停止管线


# ── LLM 调用恢复管线 ──────────────────────────────────────

@dataclass
class RecoveryContext:
    """恢复管线上下文——策略的「诊断面板」。

    调用方（Agent）填入诊断信息，策略根据这些信息表达恢复意图。
    策略只设置标志位，不执行——由 Agent 在管线返回后统一执行。
    """

    # ── 诊断（Agent 填入）────────────────
    error: Exception
    status_code: int = 0                  # HTTP 状态码（APIStatusError 自动提取）
    context_tokens: int = 0               # 当前上下文 token 估算
    tool_count: int = 0                   # 请求中的工具数量
    attempt_count: int = 0                # 本轮已尝试恢复次数（跨策略累计）
    model: str = ""                       # 当前模型名

    # ── 意图标志位（策略设置，Agent 执行）──
    compress: bool = False                # 需要压缩上下文
    reduce_tools: bool = False            # 需要精简工具列表
    switch_model: str | None = None       # 切换到指定模型
    reduce_history: bool = False          # 需要裁剪对话历史
    extra_wait: float = 0.0               # 额外等待时间（秒），0 = 不等

    # ── 限制 ────────────────────────────
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
                    return True
            except Exception:
                logger.warning("恢复策略 '%s' 异常", r.name, exc_info=True)
        return False


# ── 内置恢复策略 ──────────────────────────────────────────

class WaitRecovery(Recovery):
    """等待：瞬时 429/5xx 给网关冷却窗口"""

    name = "wait"

    def __init__(self, delay: float = 3.0, max_delay: float = 30.0):
        self.delay = delay
        self.max_delay = max_delay

    async def attempt(self, ctx: RecoveryContext) -> bool:
        if not _is_retryable(ctx):
            return False
        # 动态退避：每次重试翻倍，上限 max_delay
        delay = min(self.delay * (2 ** ctx.attempt_count), self.max_delay)
        logger.info("→ 等待 %.1fs 后重试 LLM…", delay)
        ctx.extra_wait = max(ctx.extra_wait, delay)
        return True


class ContextCompressRecovery(Recovery):
    """压缩上下文：请求体过大触发 429 时的核心恢复手段"""

    name = "compress_context"

    def __init__(self, min_context_bytes: int = 30000):
        # 低于此大小不压缩（压缩有损，尽量不碰）
        self.min_context_bytes = min_context_bytes

    async def attempt(self, ctx: RecoveryContext) -> bool:
        if not _is_retryable(ctx):
            return False
        if ctx.compress_count >= ctx.max_compress:
            return False
        # 动态判断：上下文 < min 时可能只是瞬时限流，让 WaitRecovery 处理
        if ctx.context_tokens > 0 and ctx.context_tokens * 4 < self.min_context_bytes:
            return False  # 上下文很小，压缩无意义
        logger.info("→ 压缩上下文后重试 LLM（第 %d/%d 次）",
                     ctx.compress_count + 1, ctx.max_compress)
        ctx.compress = True
        return True


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


class CallbackEmptyResponse(EmptyResponseStrategy):
    """空回复回调：注入 user 消息让 LLM 自愈。

    适用于支持 function calling 但偶尔忘记调用工具的模型。
    """

    name = "callback"

    async def attempt(self, ctx: EmptyResponseContext) -> bool:
        if ctx.retry_count >= ctx.max_retries:
            return False
        from merco.core.self_healing import empty_response
        err = empty_response()
        ctx.inject_error = err["error"]
        return True


# ── 辅助函数 ─────────────────────────────────────────────

def _is_retryable(ctx: RecoveryContext) -> bool:
    """判断错误是否可重试"""
    from merco.core.self_healing import _is_retryable_llm_error
    return _is_retryable_llm_error(ctx.error)


# ── 框架预留：动态恢复策略（当前未实现，接口已就绪）─────────
# 使用方式：
#   pipeline.use(ToolReduceRecovery(min_tools=5))
#   pipeline.use(ModelFallbackRecovery(fallback_model="gpt-4o-mini"))


class ToolReduceRecovery(Recovery):
    """精简工具：上下文过大时关闭非关键工具集 [框架预留]

    需要 Agent 支持 reduce_tools 标志位后启用。
    """

    name = "reduce_tools"

    def __init__(self, min_tools: int = 5):
        self.min_tools = min_tools

    async def attempt(self, ctx: RecoveryContext) -> bool:
        if not _is_retryable(ctx):
            return False
        if ctx.compress_count >= ctx.max_reduce:
            return False
        if ctx.tool_count <= self.min_tools:
            return False  # 工具已经很少，不再精简
        ctx.reduce_tools = True
        return True


class ModelFallbackRecovery(Recovery):
    """模型降级：当前模型不可用时切换到备选 [框架预留]

    需要 Agent 支持 switch_model 标志位后启用。
    """

    name = "model_fallback"

    def __init__(self, fallback_model: str = ""):
        self.fallback_model = fallback_model

    async def attempt(self, ctx: RecoveryContext) -> bool:
        if not _is_retryable(ctx):
            return False
        if not self.fallback_model:
            return False
        ctx.switch_model = self.fallback_model
        return True
