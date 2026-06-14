"""Memory 全链路端到端测试"""
import json
from merco.memory.store import MemoryStore
from merco.memory.save_pipeline import MemorySavePipeline, SaveItem
from merco.memory.strategy import (
    ExplicitRememberStrategy, SessionEndExtractStrategy,
)
from merco.hooks.registry import HookRegistry


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
        pipeline, llm, session_store=sess_store, min_messages=5,
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
