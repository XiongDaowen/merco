"""Observer — 订阅 hooks 事件的轻量可观察性门面"""

from merco.hooks.registry import HookRegistry
from merco.observability.metrics import MetricsCollector


class Observer:
    """Agent 可观察性门面。

    两套计数器：
    - `_live`:   当前运行（/new / /sessions 切换时 reset）
    - `_acc_map`: 跨运行累计（持久化到 SQLite，从不重置）
    """

    def __init__(self, hooks: HookRegistry):
        self._live = MetricsCollector()
        self._acc_map: dict[str, int] = {}
        self._pending_deltas: dict[str, int] = {}  # 待合并的增量

        hooks.on("llm.chat", self._on_llm)
        hooks.on("tool.after_execute", self._on_tool)
        hooks.on("tool.error", self._on_error)
        hooks.on("conversation.turn", self._on_turn)
        hooks.on("agent.interrupted", self._on_interrupt)

    # ── 事件处理 ──────────────────────────────────────────

    def _on_llm(self, duration: float = 0, tokens_in: int = 0,
                tokens_out: int = 0, cached_tokens: int = 0,
                cache_read_tokens: int = 0, **kwargs):
        self._live.increment("llm_calls")
        self._live.record_timing("llm", duration)
        if tokens_in:
            self._live.increment("tokens_in", tokens_in)
        if tokens_out:
            self._live.increment("tokens_out", tokens_out)
        cache = cached_tokens or cache_read_tokens
        if cache:
            self._live.increment("cache_hit_tokens", cache)

    def _on_tool(self, tool_name: str = "", duration: float = 0, **kwargs):
        self._live.increment("tool_calls")
        self._live.increment(f"tool.{tool_name}")
        self._live.record_timing(f"tool.{tool_name}", duration)

    def _on_error(self, tool_name: str = "", error: str = "", **kwargs):
        self._live.increment("errors")

    def _on_turn(self, **kwargs):
        self._live.increment("turns")

    def _on_interrupt(self, interrupted_tools: int = 0, **kwargs):
        """中断时记录统计。"""
        # 记录中断的 LLM 调用
        self._live.increment("llm_calls_interrupted")
        self._pending_deltas["llm_calls_interrupted"] = self._pending_deltas.get("llm_calls_interrupted", 0) + 1
        if interrupted_tools:
            self._live.increment("tool_calls_interrupted", interrupted_tools)
            self._live.increment("tool_calls", interrupted_tools)
            self._pending_deltas["tool_calls_interrupted"] = self._pending_deltas.get("tool_calls_interrupted", 0) + interrupted_tools
            self._pending_deltas["tool_calls"] = self._pending_deltas.get("tool_calls", 0) + interrupted_tools
        # 中断也算一轮（用户确实发起了请求）
        self._live.increment("turns")
        self._pending_deltas["turns"] = self._pending_deltas.get("turns", 0) + 1

    # ── 生命周期 ──────────────────────────────────────────

    def reset(self, full: bool = False):
        """清空 live 计数器。full=True 时也清空累计。"""
        self._live = MetricsCollector()
        if full:
            self._acc_map = {}

    # ── 持久化 ────────────────────────────────────────────

    def save(self):
        """存盘前：把 live 合并到 acc_map"""
        self._merge_to_acc()

    def snapshot(self) -> dict:
        """导出：live 计数器 + acc_map 累计"""
        return {
            "live": self._live.get_counters(),
            "acc": dict(self._acc_map),
        }

    def _merge_to_acc(self):
        # 只累加待合并的增量
        for k, v in self._pending_deltas.items():
            self._acc_map[k] = self._acc_map.get(k, 0) + v
        self._pending_deltas.clear()

    def restore(self, data: dict):
        """从快照恢复 acc_map"""
        self._acc_map = dict(data.get("acc", {}))

    # ── 报告 ──────────────────────────────────────────────

    def report(self) -> str:
        live = self._live
        acc = self._acc_map

        turns = live.get_counter("turns")
        llm_calls = live.get_counter("llm_calls")
        tool_calls = live.get_counter("tool_calls")
        errors = live.get_counter("errors")
        llm_avg = live.get_avg_timing("llm")
        tokens_in = live.get_counter("tokens_in")
        tokens_out = live.get_counter("tokens_out")
        cache_hit = live.get_counter("cache_hit_tokens")

        acc_turns = acc.get("turns", 0)
        acc_llm = acc.get("llm_calls", 0)
        acc_tools = acc.get("tool_calls", 0)
        acc_errors = acc.get("errors", 0)
        acc_tokens_in = acc.get("tokens_in", 0)
        acc_tokens_out = acc.get("tokens_out", 0)

        lines = ["[bold]📊 会话报告[/bold]", ""]

        # 本次
        lines.append(f"  本次: {turns} 轮  {llm_calls} 次 LLM  平均 {llm_avg:.1f}s")
        if tokens_in or tokens_out:
            ratio = f"  {cache_hit / tokens_in * 100:.0f}% 缓存命中" if tokens_in and cache_hit else ""
            lines.append(f"       入 {_fmt_n(tokens_in)} tokens  出 {_fmt_n(tokens_out)} tokens  {ratio}")
        if tool_calls:
            parts = []
            for name in sorted(live.get_counters()):
                if name.startswith("tool.") and name != "tool_calls":
                    cnt = live.get_counters().get(name, 0)
                    avg = live.get_avg_timing(name)
                    parts.append(f"[dim]{name[5:]}[/dim] {cnt}次({avg:.1f}s)")
            lines.append(f"       工具: {', '.join(parts)}" if parts else f"       工具: {tool_calls} 次")

        interrupted_tools = live.get_counter("tool_calls_interrupted")
        interrupted_llm = live.get_counter("llm_calls_interrupted")
        if interrupted_tools or interrupted_llm:
            parts = []
            if interrupted_llm:
                parts.append(f"{interrupted_llm} 次 LLM")
            if interrupted_tools:
                parts.append(f"{interrupted_tools} 次工具调用")
            lines.append(f"       [yellow]中断: {', '.join(parts)}[/yellow]")

        if errors:
            lines.append(f"       [red]错误: {errors}[/red]")

        # 累计
        if acc_turns or acc_llm or acc_tools:
            lines.append("")
            lines.append(
                f"  累计: {acc_turns + turns} 轮  {acc_llm + llm_calls} 次 LLM  "
                f"入 {_fmt_n(acc_tokens_in + tokens_in)} tokens  "
                f"出 {_fmt_n(acc_tokens_out + tokens_out)} tokens  "
                f"{acc_tools + tool_calls} 次工具"
                + (f"  [red]{acc_errors + errors} 错误[/red]" if acc_errors + errors else "")
            )

        if not turns and not acc_turns:
            lines.append("  [dim]暂无数据[/dim]")

        return "\n".join(lines)


def _fmt_n(n: int) -> str:
    if n < 1000:
        return str(n)
    return f"{n / 1024:.1f}K"
