"""TruncationProcessor — truncates large tool results."""
from __future__ import annotations

import json
import os
import time
import logging
from pathlib import Path

from merco.core.pipeline import Processor, ProcessContext, _walk_truncate, _is_reading_trunc_file

logger = logging.getLogger("merco.pipeline")


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
        lines_per_page = max(1, per_value // 60)
        ctx.result["_hint"] = (
            f"结果过长（{total_chars:,} 字符，共 {total_pages} 页）。"
            f"当前第 1 页。"
            f"➡️ 下一页: read_file {filepath} offset={lines_per_page + 1} limit={lines_per_page}"
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
