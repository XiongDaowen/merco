"""Observer 计数与报告的核心逻辑测试。"""

import pytest

from merco.hooks.registry import HookRegistry
from merco.observability.observer import Observer
from tests.conftest import MockModelProvider


@pytest.fixture
def hooks():
    return HookRegistry()


@pytest.fixture
def obs(hooks):
    return Observer(hooks)


# ── 基础场景 ─────────────────────────────────────────────


def test_fresh_session_report(obs):
    """无历史、无 live → 暂无数据。"""
    obs._live.increment("turns", 1)
    obs._live.increment("llm_calls", 1)
    r = obs.report()
    assert "本次: 1 轮  1 次 LLM" in r
    assert "暂无数据" not in r  # 有 live 数据，不算暂无


def test_accumulated_plus_live_no_merge(obs):
    """未 merge 过 → 累计 = acc + live。"""
    obs._acc_map = {"turns": 183, "llm_calls": 140}
    obs._live.increment("turns", 2)
    obs._live.increment("llm_calls", 2)
    r = obs.report()
    assert "本次: 2 轮  2 次 LLM" in r
    assert "累计: 185 轮  142 次 LLM" in r


# ── 核心 bug 复现与验证 ────────────────────────────────────


def test_report_after_merge_no_double_count(obs):
    """merge 后 report 不重复计数 — 根本 bug 场景。"""
    # 模拟历史数据
    obs._acc_map = {"turns": 183, "llm_calls": 140}
    # 当前会话跑了 2 轮
    obs._live.increment("turns", 2)
    obs._live.increment("llm_calls", 2)

    # 第一次 report（merge 前）
    r1 = obs.report()
    assert "累计: 185 轮  142 次 LLM" in r1

    # 中断后 _on_interrupt 加 1 轮
    obs._on_interrupt(interrupted_tools=0)
    assert obs._live.get_counter("turns") == 3

    # SavePartialState → save → _merge_to_acc
    obs.save()

    # merge 后 _live 没有重置
    assert obs._live.get_counter("turns") == 3

    # report 不应重复计数
    r2 = obs.report()
    assert "本次: 3 轮" in r2
    assert "累计: 186 轮  142 次 LLM" in r2  # 不是 189


def test_report_after_merge_then_more_activity(obs):
    """merge 后继续跑 → 累计 = acc + 新增增量。"""
    obs._acc_map = {"turns": 183}
    obs._live.increment("turns", 2)

    # 中断 → merge
    obs._on_interrupt(interrupted_tools=0)
    obs.save()
    # 此时 acc.turns = 186, last_merged.turns = 3

    # 继续跑 2 轮
    obs._live.increment("turns", 2)
    assert obs._live.get_counter("turns") == 5

    r = obs.report()
    assert "本次: 5 轮" in r
    # 累计 = 186(acc) + (5-3)(unmerged) = 188
    assert "累计: 188 轮" in r


# ── session 切换 ─────────────────────────────────────────


def test_reset_clears_last_merged(obs):
    """reset() 清空 _last_merged，切会话后新增量正确计算。"""
    obs._acc_map = {"turns": 100}
    obs._live.increment("turns", 5)
    obs.save()  # acc.turns = 105, last_merged.turns = 5
    assert obs._acc_map["turns"] == 105

    # 切会话：不 full，不清 acc
    obs.reset(full=False)
    assert obs._acc_map["turns"] == 105  # acc 保留
    assert obs._last_merged == {}

    # 新会话跑 2 轮
    obs._live.increment("turns", 2)
    r = obs.report()
    # 累计 = 105(acc) + 2(未 merge 的增量) = 107
    assert "累计: 107 轮" in r


def test_restore_then_report(obs):
    """restore 后 report → acc + live（last_merged 为空）。"""
    obs.restore({"acc": {"turns": 186, "llm_calls": 148}})
    obs._live.increment("turns", 2)
    obs._live.increment("llm_calls", 2)
    r = obs.report()
    assert "本次: 2 轮  2 次 LLM" in r
    assert "累计: 188 轮  150 次 LLM" in r


# ── 中断统计 ─────────────────────────────────────────────


def test_on_interrupt_counts(obs):
    """中断计入 live 的中断计数和工具调用。"""
    obs._on_interrupt(interrupted_tools=2)
    assert obs._live.get_counter("tool_calls_interrupted") == 2
    assert obs._live.get_counter("llm_calls_interrupted") == 1
    assert obs._live.get_counter("tool_calls") == 2
    assert obs._live.get_counter("turns") == 1


def test_on_interrupt_report_shows_yellow(obs):
    """中断后 report 显示黄色中断行。"""
    obs._on_interrupt(interrupted_tools=1)
    r = obs.report()
    assert "中断:" in r
    assert "1 次 LLM" in r
    assert "1 次工具调用" in r


# ── _merge_to_acc 增量正确性 ──────────────────────────────


def test_merge_to_acc_only_adds_delta(obs):
    """_merge_to_acc 只累加增量，不重复加已合并部分。"""
    obs._live.increment("turns", 5)
    obs._merge_to_acc()
    assert obs._acc_map["turns"] == 5
    assert obs._last_merged["turns"] == 5

    # 再跑 3 轮
    obs._live.increment("turns", 3)
    obs._merge_to_acc()
    assert obs._acc_map["turns"] == 8  # 5 + 3
    assert obs._last_merged["turns"] == 8


def test_merge_to_acc_idempotent(obs):
    """连续 merge 不变 — 增量为 0。"""
    obs._live.increment("turns", 5)
    obs._merge_to_acc()
    obs._merge_to_acc()  # 再次
    assert obs._acc_map["turns"] == 5  # 不变


# ── 大数字格式化 ─────────────────────────────────────────


def test_fmt_n():
    from merco.observability.observer import _fmt_n

    assert _fmt_n(999) == "999"
    assert _fmt_n(1024) == "1.0K"
    assert _fmt_n(1048576) == "1024.0K"


# ── snapshot / restore round-trip ─────────────────────────


def test_snapshot_restore_roundtrip(obs):
    """snapshot → restore → acc_map 不变。"""
    obs._acc_map = {"turns": 42, "llm_calls": 30}
    data = obs.snapshot()
    obs2 = Observer(HookRegistry())
    obs2.restore(data)
    assert obs2._acc_map == {"turns": 42, "llm_calls": 30}


# ── Hook 事件计数 during agent loop ───────────────────────


@pytest.mark.asyncio
async def test_observer_counts_hook_events_in_agent_loop(test_agent, monkeypatch):
    """agent.run() 触发后，Observer 内部计数应正确更新。

    验证 _live 计数器在一次 run（包含 LLM 调用 + 工具执行 + conversation turn）之后
    被 hook 事件正确填充。counter key 名（来自 observer.py）：
    - llm_calls, tokens_in, tokens_out
    - tool_calls, tool.{name}
    - turns
    - agent_starts, agent_stops
    """
    from io import StringIO

    from rich.console import Console

    # 替换 console 避免噪声
    quiet = Console(file=StringIO(), force_terminal=True, width=120)
    monkeypatch.setattr("merco.core.agent.console", quiet)

    # test_agent fixture 已经在 agent.py:328 自动创建 self.observer
    observer = test_agent.observer
    # 确保计数从干净状态开始
    observer.reset(full=False)

    # Mock LLM：第一次 tool_call → 第二次 final answer
    test_agent.provider = MockModelProvider(
        [
            {"tool_calls": [{"id": "t1", "name": "echo", "arguments": {"message": "hi"}}]},
            {"content": "done"},
        ]
    )

    # 跑一轮带工具调用
    await test_agent.run("echo hi")

    # 验证 Observer live 计数（key 名以 observer.py:36, 47, 55 为准）
    counters = observer._live.get_counters()

    # agent.start + agent.stop 都会触发
    assert counters.get("agent_starts", 0) >= 1
    assert counters.get("agent_stops", 0) >= 1

    # 至少 2 次 LLM 调用（tool_call 一次，final 一次）
    assert counters.get("llm_calls", 0) >= 2

    # tool.after_execute 至少 1 次
    assert counters.get("tool_calls", 0) >= 1
    assert counters.get("tool.echo", 0) >= 1

    # conversation.turn 至少 1 次
    assert counters.get("turns", 0) >= 1
