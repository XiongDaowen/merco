"""MemorySaveStrategy 单测"""

import json

import pytest

from merco.memory.strategy import ExplicitRememberStrategy, MemorySaveStrategy, SessionEndExtractStrategy


class FakePipeline:
    def __init__(self):
        self.saved = []

    async def save(self, item):
        self.saved.append(item)
        return True


class FakeStrategy(MemorySaveStrategy):
    name = "fake"

    def __init__(self, pipeline):
        super().__init__(pipeline)
        self.handled = []

    async def on_event(self, event, **kwargs):
        self.handled.append((event, kwargs))


def test_strategy_name_default():
    """基类 name 默认空字符串"""
    s = FakeStrategy(FakePipeline())
    assert s.name == "fake"  # 子类覆盖


def test_strategy_holds_pipeline_ref():
    """Strategy 持有 pipeline 引用"""
    p = FakePipeline()
    s = FakeStrategy(p)
    assert s.pipeline is p


async def test_explicit_remember_uses_given_key():
    """显式 key 时直接用"""
    p = FakePipeline()
    s = ExplicitRememberStrategy(p)
    await s.on_event("command.remember", text="hello", key="my_key")
    assert len(p.saved) == 1
    assert p.saved[0].key == "my_key"
    assert p.saved[0].value == "hello"
    assert p.saved[0].source == "user"


async def test_explicit_remember_auto_derives_key():
    """无 key 时自动派生"""
    p = FakePipeline()
    s = ExplicitRememberStrategy(p)
    await s.on_event("command.remember", text="我喜欢用中文交流")
    assert len(p.saved) == 1
    assert p.saved[0].key.startswith("user_")
    assert "我喜欢" in p.saved[0].key or len(p.saved[0].key) > 10


async def test_explicit_derive_key_stable_for_same_text():
    """相同文本派生相同 key"""
    k1 = ExplicitRememberStrategy._derive_key("hello world")
    k2 = ExplicitRememberStrategy._derive_key("hello world")
    assert k1 == k2


async def test_explicit_derive_key_handles_special_chars():
    """特殊字符 → 下划线"""
    k = ExplicitRememberStrategy._derive_key("hello! @world#")
    assert "!" not in k
    assert "@" not in k
    assert "#" not in k


def test_explicit_subscribe_registers_handler():
    """subscribe() 注册到 hooks"""

    class FakeHooks:
        def __init__(self):
            self.handlers = {}

        def on(self, event, handler):
            self.handlers[event] = handler

    hooks = FakeHooks()
    s = ExplicitRememberStrategy(FakePipeline())
    s.subscribe(hooks)
    assert "command.remember" in hooks.handlers
    assert hooks.handlers["command.remember"] == s._on_remember


class FakeLLM:
    def __init__(self, content=""):
        self._content = content
        self.calls = []

    async def chat(self, messages, tools=None, tool_choice="auto"):
        self.calls.append(messages)
        return {"content": self._content}


class FakeSessionStore:
    def __init__(self, messages=None):
        self._msgs = messages or []

    def load_messages(self, session_id):
        return self._msgs


@pytest.mark.asyncio
async def test_session_end_skips_too_short():
    """< min_messages 跳过"""
    p = FakePipeline()
    llm = FakeLLM(content="[]")
    store = FakeSessionStore(messages=[{"role": "user", "content": "hi"}])
    s = SessionEndExtractStrategy(p, lambda: llm, session_store=store, min_messages=5)
    await s.on_event("session.destroy", session_id="s1")
    assert p.saved == []
    assert llm.calls == []  # 没调 LLM


@pytest.mark.asyncio
async def test_session_end_extracts_and_saves():
    """正常对话 → 调 LLM → 解析 → 存"""
    p = FakePipeline()
    msgs = [{"role": "user", "content": f"msg{i}"} for i in range(6)]
    llm_content = json.dumps(
        [
            {"key": "user_prefers_chinese", "value": "用户偏好中文", "tags": ["lang"]},
            {"key": "user_name", "value": "用户叫小王", "tags": []},
        ]
    )
    llm = FakeLLM(content=llm_content)
    store = FakeSessionStore(messages=msgs)
    s = SessionEndExtractStrategy(p, lambda: llm, session_store=store, min_messages=5)
    await s.on_event("session.destroy", session_id="s1")
    assert len(p.saved) == 2
    assert p.saved[0].source == "extracted"
    assert p.saved[0].session_id == "s1"
    assert p.saved[0].key == "user_prefers_chinese"


@pytest.mark.asyncio
async def test_session_end_caps_max_per_session():
    """max_per_session 截断"""
    p = FakePipeline()
    msgs = [{"role": "user", "content": f"msg{i}"} for i in range(6)]
    items = [{"key": f"k{i}", "value": f"v{i}", "tags": []} for i in range(10)]
    llm = FakeLLM(content=json.dumps(items))
    store = FakeSessionStore(messages=msgs)
    s = SessionEndExtractStrategy(p, lambda: llm, session_store=store, min_messages=5, max_per_session=2)
    await s.on_event("session.destroy", session_id="s1")
    assert len(p.saved) == 2


@pytest.mark.asyncio
async def test_session_end_swallows_llm_errors():
    """LLM 失败不抛（fail-soft）"""
    p = FakePipeline()
    msgs = [{"role": "user", "content": f"msg{i}"} for i in range(6)]

    class FailingLLM:
        async def chat(self, *args, **kwargs):
            raise RuntimeError("network down")

    store = FakeSessionStore(messages=msgs)
    s = SessionEndExtractStrategy(p, lambda: FailingLLM(), session_store=store, min_messages=5)
    # 不应抛
    await s.on_event("session.destroy", session_id="s1")
    assert p.saved == []


@pytest.mark.asyncio
async def test_session_end_handles_invalid_json():
    """LLM 返回非 JSON → 整批丢弃"""
    p = FakePipeline()
    msgs = [{"role": "user", "content": f"msg{i}"} for i in range(6)]
    llm = FakeLLM(content="not a json")
    store = FakeSessionStore(messages=msgs)
    s = SessionEndExtractStrategy(p, lambda: llm, session_store=store, min_messages=5)
    await s.on_event("session.destroy", session_id="s1")
    assert p.saved == []
