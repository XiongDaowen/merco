"""Memory 全链路端到端测试"""

import json

import pytest

from merco.hooks.registry import HookRegistry
from merco.memory.save_pipeline import MemorySavePipeline, SaveItem
from merco.memory.store import MemoryStore
from merco.memory.strategy import (
    ExplicitRememberStrategy,
    SessionEndExtractStrategy,
)
from tests.conftest import MockModelProvider


class FakeLLM:
    def __init__(self, content="[]"):
        self._content = content

    async def chat(self, messages, tools=None, tool_choice="auto"):
        return {"content": self._content}


class FakeSessionStore:
    def __init__(self, messages=None):
        self._msgs = messages or []

    def load_messages(self, session_id):
        return self._msgs


async def test_full_lifecycle_explicit_remember(tmp_path):
    """Hook → Strategy → Pipeline → Store → Observer 全链路"""
    hooks = HookRegistry()
    store = MemoryStore(str(tmp_path / "memory"))

    saved_events = []

    async def on_saved(key, **kwargs):
        saved_events.append(key)

    hooks.on("memory.saved", on_saved)

    pipeline = MemorySavePipeline(store, hooks)
    strategy = ExplicitRememberStrategy(pipeline)
    strategy.subscribe(hooks)

    # 模拟 /remember 命令触发
    await hooks.emit("command.remember", text="我喜欢用中文", key="user_lang")

    # 验证存入了
    record = store.load("user_lang")
    assert record is not None
    assert record["value"] == "我喜欢用中文"
    assert "[user]" in record["tags"]

    # 验证 Observer 收到了事件
    assert "user_lang" in saved_events


async def test_full_lifecycle_session_end_extract(tmp_path):
    """session.destroy 触发 LLM 抽取 → 存入"""
    hooks = HookRegistry()
    store = MemoryStore(str(tmp_path / "memory"))
    pipeline = MemorySavePipeline(store, hooks)

    saved_events = []

    async def on_saved(key, **kwargs):
        saved_events.append(key)

    hooks.on("memory.saved", on_saved)

    msgs = [{"role": "user", "content": f"msg {i}"} for i in range(6)]
    llm_content = json.dumps([{"key": "user_k", "value": "v", "tags": []}])
    sess_store = FakeSessionStore(messages=msgs)
    llm = FakeLLM(content=llm_content)

    strategy = SessionEndExtractStrategy(
        pipeline,
        lambda: llm,
        session_store=sess_store,
        min_messages=5,
    )
    strategy.subscribe(hooks)

    # 模拟 session.destroy
    await hooks.emit("session.destroy", session_id="s1")

    record = store.load("user_k")
    assert record is not None
    assert record["value"] == "v"
    assert "[extracted]" in record["tags"]
    assert "user_k" in saved_events


async def test_dedup_user_beats_extracted(tmp_path):
    """显式 /remember 优先于 extracted（不会覆盖）"""
    hooks = HookRegistry()
    store = MemoryStore(str(tmp_path / "memory"))
    pipeline = MemorySavePipeline(store, hooks)

    # 先存一条 user
    exp = ExplicitRememberStrategy(pipeline)
    exp.subscribe(hooks)
    await hooks.emit("command.remember", text="我的偏好", key="preference")

    # 再模拟 extracted 来覆盖（应被 skip）
    record1 = store.load("preference")
    assert record1["value"] == "我的偏好"
    # 手动模拟 extracted 写入（构造 SaveItem 走 Pipeline）
    item = SaveItem(key="preference", value="AI 猜测的偏好", source="extracted")
    result = await pipeline.save(item)
    assert result is False  # 被 dedup skip
    record2 = store.load("preference")
    assert record2["value"] == "我的偏好"  # 未覆盖


@pytest.mark.asyncio
async def test_recall_injects_into_system_prompt(test_agent):
    """存记忆 → agent.run() → system prompt 含记忆内容"""
    # 存记忆
    test_agent._memory_store.save("user_name", "小王", tags=["[user]"])

    # 构造会让系统调用 recaller 的 user prompt
    test_agent.provider = MockModelProvider([{"content": "你好小王"}])

    # 跑一轮 — query 包含 "user_name" 以触发 MemoryStore.search 命中
    # (MemoryStore.search 是简单子串匹配：把 query 与 json.dumps(record) 比对。
    #  中文在 JSON 中被转义为 \uXXXX，所以用 key 名称 "user_name" 作为查询词
    #  才能匹配到记录。查询词必须是 JSON dump 的子串。)
    await test_agent.run("user_name")

    # 验证：system prompt 包含记忆
    # context.messages[0] 是 user 消息（system prompt 只在 LLM 调用的 messages 列表里），
    # 所以我们检查 LLM 收到的消息中的 system 内容
    assert len(test_agent.provider.calls) >= 1
    llm_messages = test_agent.provider.calls[0]["messages"]
    sys_msg = llm_messages[0]
    assert sys_msg["role"] == "system"
    # 拼接所有 system chunk（_build_system_prompt 可能在多个 system 消息里）
    all_sys = sys_msg.get("content", "")
    for m in llm_messages[1:]:
        if m.get("role") == "system":
            all_sys += m.get("content", "")
    assert "小王" in all_sys or "user_name" in all_sys


async def test_memory_save_emits_event(test_agent):
    """/remember → Strategy → Pipeline → Store + memory.saved 事件"""
    # 注册事件 handler
    saved_events = []

    async def on_saved(key, **kwargs):
        saved_events.append(key)

    test_agent.hooks.on("memory.saved", on_saved)

    # 触发 command.remember
    await test_agent.hooks.emit("command.remember", text="我喜欢用中文", key="user_lang_pref")

    # 验证：store 写入成功
    record = test_agent._memory_store.load("user_lang_pref")
    assert record is not None
    assert record["value"] == "我喜欢用中文"
    assert "[user]" in record["tags"]

    # 验证：memory.saved 事件触发
    assert "user_lang_pref" in saved_events
