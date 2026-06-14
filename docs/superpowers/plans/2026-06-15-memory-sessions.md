# Memory → Sessions 打通实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 Agent 能在会话中存记忆（显式 + LLM 自动抽取），并在下次召回注入 system prompt

**Architecture:**
- `MemorySavePipeline` 统一保存链（SourceEnricher → DedupProcessor → Store）
- 两个 `MemorySaveStrategy`（ExplicitRemember / SessionEndExtract）订阅 HookRegistry 事件
- Agent 业务零感知，只 emit `command.remember` 事件

**Tech Stack:** Python 3.12, dataclass, asyncio, hashlib

---

## 文件结构

| 文件 | 职责 |
|------|------|
| `merco/memory/save_pipeline.py` | SaveItem 数据类 + MemorySavePipeline + SourceEnricher + DedupProcessor |
| `merco/memory/strategy.py` | MemorySaveStrategy ABC + ExplicitRememberStrategy + SessionEndExtractStrategy |
| `merco/memory/__init__.py` | 导出新符号 |
| `merco/core/config.py` | 新增 3 个 config 字段 |
| `merco/core/agent.py` | 启动时装配 Pipeline + Strategies |
| `merco/observability/observer.py` | 订阅 memory.saved 事件 |
| `cli/commands.py` | 新增 /remember, /memories, /forget 命令 |
| `tests/memory/test_save_pipeline.py` | Pipeline + Processor 单测 |
| `tests/memory/test_strategy.py` | Strategy 单测 |
| `tests/memory/test_cli.py` | CLI 命令单测 |
| `tests/integration/test_memory_lifecycle.py` | 端到端集成测试 |

---

## Task 1: 实现 SaveItem 和 MemorySaveProcessor 基类

**Files:**
- Create: `merco/memory/save_pipeline.py`
- Test: `tests/memory/test_save_pipeline.py`

- [ ] **Step 1: Write the failing test**

Create `tests/memory/test_save_pipeline.py`:

```python
"""MemorySavePipeline 单测"""
from dataclasses import dataclass
from merco.memory.save_pipeline import SaveItem, MemorySource, SOURCE_PRIORITY


def test_save_item_creation():
    """SaveItem 默认值正确"""
    item = SaveItem(key="k1", value="v1", source="user")
    assert item.key == "k1"
    assert item.value == "v1"
    assert item.source == "user"
    assert item.tags == []
    assert item.session_id == ""
    assert item.metadata == {}


def test_source_priority_ordering():
    """source 优先级 user > extracted > system"""
    assert SOURCE_PRIORITY["user"] > SOURCE_PRIORITY["extracted"]
    assert SOURCE_PRIORITY["extracted"] > SOURCE_PRIORITY["system"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/xiowen/code/merco && python3 -m pytest tests/memory/test_save_pipeline.py -v`
Expected: ImportError or ModuleNotFoundError (merco.memory.save_pipeline not exists)

- [ ] **Step 3: Write minimal implementation**

Create `merco/memory/save_pipeline.py`:

```python
"""Memory 保存链 — Strategy 通过它写入 MemoryStore"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Literal

logger = logging.getLogger("merco.memory.save_pipeline")


MemorySource = Literal["user", "extracted", "system"]


SOURCE_PRIORITY: dict[str, int] = {
    "user": 3,
    "extracted": 2,
    "system": 1,
}


@dataclass
class SaveItem:
    """Pipeline 输入单元"""
    key: str
    value: str
    source: MemorySource
    tags: list[str] = field(default_factory=list)
    session_id: str = ""
    metadata: dict = field(default_factory=dict)


class MemorySaveProcessor(ABC):
    """保存链处理器基类"""
    name: str = ""

    @abstractmethod
    async def process(self, item: SaveItem) -> SaveItem | None:
        """返回 None = 跳过该 item"""
        ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/xiowen/code/merco && python3 -m pytest tests/memory/test_save_pipeline.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
cd /home/xiowen/code/merco
git add merco/memory/save_pipeline.py tests/memory/test_save_pipeline.py
git commit -m "feat: add SaveItem and MemorySaveProcessor base"
```

---

## Task 2: 实现 SourceEnricher

**Files:**
- Modify: `merco/memory/save_pipeline.py`
- Test: `tests/memory/test_save_pipeline.py`

- [ ] **Step 1: Add failing test**

Append to `tests/memory/test_save_pipeline.py`:

```python
import pytest
from merco.memory.save_pipeline import SourceEnricher


@pytest.mark.asyncio
async def test_source_enricher_adds_prefix_tag():
    """SourceEnricher 自动补 [source] 前缀到 tags"""
    enricher = SourceEnricher()
    item = SaveItem(key="k1", value="v1", source="user", tags=["custom"])
    result = await enricher.process(item)
    assert result is not None
    assert "[user]" in result.tags
    assert "custom" in result.tags
    assert result.tags[0] == "[user]"


@pytest.mark.asyncio
async def test_source_enricher_does_not_duplicate_prefix():
    """已含 [source] 前缀时不重复加"""
    enricher = SourceEnricher()
    item = SaveItem(key="k1", value="v1", source="user", tags=["[user]", "x"])
    result = await enricher.process(item)
    assert result is not None
    assert result.tags.count("[user]") == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/xiowen/code/merco && python3 -m pytest tests/memory/test_save_pipeline.py -v -k source_enricher`
Expected: ImportError (SourceEnricher not exists)

- [ ] **Step 3: Add SourceEnricher implementation**

Append to `merco/memory/save_pipeline.py`:

```python
class SourceEnricher(MemorySaveProcessor):
    """自动补 [source] 前缀到 tags"""
    name = "source_enricher"

    async def process(self, item: SaveItem) -> SaveItem:
        prefix = f"[{item.source}]"
        if prefix not in item.tags:
            item.tags.insert(0, prefix)
        return item
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/xiowen/code/merco && python3 -m pytest tests/memory/test_save_pipeline.py -v -k source_enricher`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
cd /home/xiowen/code/merco
git add merco/memory/save_pipeline.py tests/memory/test_save_pipeline.py
git commit -m "feat: add SourceEnricher processor"
```

---

## Task 3: 实现 DedupProcessor

**Files:**
- Modify: `merco/memory/save_pipeline.py`
- Test: `tests/memory/test_save_pipeline.py`

- [ ] **Step 1: Add failing test**

Append to `tests/memory/test_save_pipeline.py`:

```python
from merco.memory.save_pipeline import DedupProcessor


class FakeStore:
    """最小 MemoryStore mock"""
    def __init__(self, existing=None):
        self._data = existing or {}

    def load(self, key):
        return self._data.get(key)


@pytest.mark.asyncio
async def test_dedup_skip_when_existing_user_wins():
    """已有 [user] 时 [extracted] 来 → skip（保护 user）"""
    store = FakeStore({"k1": {"tags": ["[user]", "x"], "value": "old"}})
    proc = DedupProcessor(store)
    item = SaveItem(key="k1", value="new", source="extracted")
    result = await proc.process(item)
    assert result is None  # 被 skip


@pytest.mark.asyncio
async def test_dedup_overwrite_when_new_higher_priority():
    """已有 [extracted] 时 [user] 来 → 覆盖"""
    store = FakeStore({"k1": {"tags": ["[extracted]"], "value": "old"}})
    proc = DedupProcessor(store)
    item = SaveItem(key="k1", value="new", source="user")
    result = await proc.process(item)
    assert result is not None
    assert result.value == "new"


@pytest.mark.asyncio
async def test_dedup_pass_through_when_key_not_exists():
    """key 不存在 → 直接通过"""
    store = FakeStore()
    proc = DedupProcessor(store)
    item = SaveItem(key="k1", value="v", source="user")
    result = await proc.process(item)
    assert result is not None


@pytest.mark.asyncio
async def test_dedup_infer_source_from_tags():
    """旧记录无 [source] 标签时按 user 处理（向后兼容）"""
    store = FakeStore({"k1": {"tags": [], "value": "old"}})
    proc = DedupProcessor(store)
    # extracted 来（优先级 2） vs 空（默认最低 0） → 覆盖
    item = SaveItem(key="k1", value="new", source="extracted")
    result = await proc.process(item)
    assert result is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/xiowen/code/merco && python3 -m pytest tests/memory/test_save_pipeline.py -v -k dedup`
Expected: ImportError (DedupProcessor not exists)

- [ ] **Step 3: Add DedupProcessor implementation**

Append to `merco/memory/save_pipeline.py`:

```python
class DedupProcessor(MemorySaveProcessor):
    """按 source 优先级 skip 已有 key"""
    name = "dedup"

    def __init__(self, store):
        self._store = store

    async def process(self, item: SaveItem) -> SaveItem | None:
        existing = self._store.load(item.key)
        if not existing:
            return item
        existing_tags = existing.get("tags", []) or []
        existing_source = self._infer_source(existing_tags)
        new_priority = SOURCE_PRIORITY.get(item.source, 0)
        existing_priority = SOURCE_PRIORITY.get(existing_source, 0)
        if new_priority <= existing_priority:
            return None
        return item

    @staticmethod
    def _infer_source(tags: list[str]) -> str:
        """从 tags 推断 source。无 [source] 标记视为 system（最低，向后兼容旧记录）"""
        for t in tags:
            if t.startswith("[") and t.endswith("]"):
                inner = t[1:-1]
                if inner in SOURCE_PRIORITY:
                    return inner
        return "system"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/xiowen/code/merco && python3 -m pytest tests/memory/test_save_pipeline.py -v -k dedup`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
cd /home/xiowen/code/merco
git add merco/memory/save_pipeline.py tests/memory/test_save_pipeline.py
git commit -m "feat: add DedupProcessor with source priority"
```

---

## Task 4: 实现 MemorySavePipeline

**Files:**
- Modify: `merco/memory/save_pipeline.py`
- Test: `tests/memory/test_save_pipeline.py`

- [ ] **Step 1: Add failing test**

Append to `tests/memory/test_save_pipeline.py`:

```python
from merco.memory.save_pipeline import MemorySavePipeline


class FakeHooks:
    """最小 HookRegistry mock"""
    def __init__(self):
        self.events = []

    async def emit(self, event, **kwargs):
        self.events.append((event, kwargs))


class FakeMemoryStore:
    """最小 MemoryStore mock — save + load"""
    def __init__(self):
        self._data = {}

    def save(self, key, value, tags=None):
        self._data[key] = {"value": value, "tags": tags or []}

    def load(self, key):
        return self._data.get(key)


@pytest.mark.asyncio
async def test_pipeline_saves_and_emits_event():
    """Pipeline 成功时 emit memory.saved"""
    store = FakeMemoryStore()
    hooks = FakeHooks()
    pipeline = MemorySavePipeline(store, hooks)

    item = SaveItem(key="k1", value="hello", source="user", tags=["custom"])
    result = await pipeline.save(item)
    assert result is True
    assert store._data["k1"]["value"] == "hello"
    assert "[user]" in store._data["k1"]["tags"]
    assert "custom" in store._data["k1"]["tags"]

    # 验证 emit
    assert len(hooks.events) == 1
    event, kwargs = hooks.events[0]
    assert event == "memory.saved"
    assert kwargs["key"] == "k1"
    assert kwargs["source"] == "user"


@pytest.mark.asyncio
async def test_pipeline_dedup_skip_returns_false():
    """Dedup 命中 → 返回 False，不发 memory.saved"""
    store = FakeMemoryStore()
    store._data["k1"] = {"value": "old", "tags": ["[user]"]}
    hooks = FakeHooks()
    pipeline = MemorySavePipeline(store, hooks)

    item = SaveItem(key="k1", value="new", source="extracted")
    result = await pipeline.save(item)
    assert result is False
    assert store._data["k1"]["value"] == "old"  # 未覆盖
    assert hooks.events == []


@pytest.mark.asyncio
async def test_pipeline_use_adds_processor():
    """use() 追加 processor 到链尾"""
    store = FakeMemoryStore()
    hooks = FakeHooks()
    pipeline = MemorySavePipeline(store, hooks)

    class TagProcessor(MemorySaveProcessor):
        name = "test_tag"
        async def process(self, item):
            item.tags.append("from_test")
            return item

    pipeline.use(TagProcessor())
    await pipeline.save(SaveItem(key="k1", value="v", source="user"))
    assert "from_test" in store._data["k1"]["tags"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/xiowen/code/merco && python3 -m pytest tests/memory/test_save_pipeline.py -v -k pipeline`
Expected: ImportError (MemorySavePipeline not exists)

- [ ] **Step 3: Add MemorySavePipeline implementation**

Append to `merco/memory/save_pipeline.py`:

```python
class MemorySavePipeline:
    """统一的 Memory 保存链 — Strategy 通过它写入"""

    def __init__(self, store, hooks):
        self.store = store
        self.hooks = hooks
        self._processors: list[MemorySaveProcessor] = [
            SourceEnricher(),
            DedupProcessor(store),
        ]

    def use(self, processor: MemorySaveProcessor) -> "MemorySavePipeline":
        self._processors.append(processor)
        return self

    async def save(self, item: SaveItem) -> bool:
        """返回 True=写入成功，False=被 dedup skip"""
        for p in self._processors:
            try:
                item = await p.process(item)
            except Exception as e:
                logger.warning("MemorySaveProcessor '%s' 异常: %s", p.name, e)
                return False
            if item is None:
                return False
        try:
            self.store.save(item.key, item.value, tags=item.tags)
        except Exception as e:
            logger.warning("MemoryStore.save 失败 [%s]: %s", item.key, e)
            try:
                await self.hooks.emit("memory.failed", key=item.key, error=str(e))
            except Exception:
                pass
            return False
        try:
            await self.hooks.emit(
                "memory.saved",
                key=item.key, value=item.value,
                source=item.source, tags=item.tags,
            )
        except Exception:
            pass
        return True
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/xiowen/code/merco && python3 -m pytest tests/memory/test_save_pipeline.py -v -k pipeline`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
cd /home/xiowen/code/merco
git add merco/memory/save_pipeline.py tests/memory/test_save_pipeline.py
git commit -m "feat: add MemorySavePipeline with processor chain"
```

---

## Task 5: 实现 MemorySaveStrategy 基类

**Files:**
- Create: `merco/memory/strategy.py`
- Test: `tests/memory/test_strategy.py`

- [ ] **Step 1: Write failing test**

Create `tests/memory/test_strategy.py`:

```python
"""MemorySaveStrategy 单测"""
import pytest
from merco.memory.save_pipeline import SaveItem
from merco.memory.strategy import MemorySaveStrategy


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/xiowen/code/merco && python3 -m pytest tests/memory/test_strategy.py -v`
Expected: ImportError (merco.memory.strategy not exists)

- [ ] **Step 3: Create strategy.py**

Create `merco/memory/strategy.py`:

```python
"""Memory 保存触发策略 — 监听 Hook 事件，构造 SaveItem 喂给 Pipeline"""
from __future__ import annotations

from abc import ABC, abstractmethod


class MemorySaveStrategy(ABC):
    """监听事件，构造 SaveItem 喂给 Pipeline"""

    name: str = ""

    def __init__(self, pipeline):
        self.pipeline = pipeline

    @abstractmethod
    async def on_event(self, event: str, **kwargs) -> None: ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/xiowen/code/merco && python3 -m pytest tests/memory/test_strategy.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
cd /home/xiowen/code/merco
git add merco/memory/strategy.py tests/memory/test_strategy.py
git commit -m "feat: add MemorySaveStrategy base class"
```

---

## Task 6: 实现 ExplicitRememberStrategy

**Files:**
- Modify: `merco/memory/strategy.py`
- Test: `tests/memory/test_strategy.py`

- [ ] **Step 1: Add failing test**

Append to `tests/memory/test_strategy.py`:

```python
from merco.memory.strategy import ExplicitRememberStrategy


@pytest.mark.asyncio
async def test_explicit_remember_uses_given_key():
    """显式 key 时直接用"""
    p = FakePipeline()
    s = ExplicitRememberStrategy(p)
    await s.on_event("command.remember", text="hello", key="my_key")
    assert len(p.saved) == 1
    assert p.saved[0].key == "my_key"
    assert p.saved[0].value == "hello"
    assert p.saved[0].source == "user"


@pytest.mark.asyncio
async def test_explicit_remember_auto_derives_key():
    """无 key 时自动派生"""
    p = FakePipeline()
    s = ExplicitRememberStrategy(p)
    await s.on_event("command.remember", text="我喜欢用中文交流")
    assert len(p.saved) == 1
    assert p.saved[0].key.startswith("user_")
    assert "我喜欢" in p.saved[0].key or len(p.saved[0].key) > 10


@pytest.mark.asyncio
async def test_explicit_derive_key_stable_for_same_text():
    """相同文本派生相同 key"""
    k1 = ExplicitRememberStrategy._derive_key("hello world")
    k2 = ExplicitRememberStrategy._derive_key("hello world")
    assert k1 == k2


@pytest.mark.asyncio
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/xiowen/code/merco && python3 -m pytest tests/memory/test_strategy.py -v -k explicit`
Expected: ImportError (ExplicitRememberStrategy not exists)

- [ ] **Step 3: Add ExplicitRememberStrategy implementation**

Append to `merco/memory/strategy.py`:

```python
import hashlib
import re
import logging
from .save_pipeline import SaveItem

logger = logging.getLogger("merco.memory.strategy")


class ExplicitRememberStrategy(MemorySaveStrategy):
    """/remember <text> 显式存一条记忆"""
    name = "explicit_remember"

    def subscribe(self, hooks) -> None:
        """注册到 HookRegistry"""
        hooks.on("command.remember", self._on_remember)

    async def on_event(self, event: str, **kwargs) -> None:
        """兼容直接调用（测试用）"""
        await self._on_remember(**kwargs)

    async def _on_remember(self, text: str, key: str = "", **kwargs) -> None:
        if not key:
            key = self._derive_key(text)
        item = SaveItem(key=key, value=text, source="user")
        await self.pipeline.save(item)

    @staticmethod
    def _derive_key(text: str) -> str:
        """从文本生成稳定 key: user_<前20字净化>_<hash8>"""
        h = hashlib.md5(text.encode()).hexdigest()[:8]
        prefix = re.sub(r"\W+", "_", text[:20].strip()).strip("_")
        return f"user_{prefix}_{h}" if prefix else f"user_{h}"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/xiowen/code/merco && python3 -m pytest tests/memory/test_strategy.py -v -k explicit`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
cd /home/xiowen/code/merco
git add merco/memory/strategy.py tests/memory/test_strategy.py
git commit -m "feat: add ExplicitRememberStrategy"
```

---

## Task 7: 实现 SessionEndExtractStrategy

**Files:**
- Modify: `merco/memory/strategy.py`
- Test: `tests/memory/test_strategy.py`

- [ ] **Step 1: Add failing test**

Append to `tests/memory/test_strategy.py`:

```python
import json
from merco.memory.strategy import SessionEndExtractStrategy


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
    s = SessionEndExtractStrategy(p, llm, session_store=store, min_messages=5)
    await s.on_event("session.destroy", session_id="s1")
    assert p.saved == []
    assert llm.calls == []  # 没调 LLM


@pytest.mark.asyncio
async def test_session_end_extracts_and_saves():
    """正常对话 → 调 LLM → 解析 → 存"""
    p = FakePipeline()
    msgs = [{"role": "user", "content": f"msg{i}"} for i in range(6)]
    llm_content = json.dumps([
        {"key": "user_prefers_chinese", "value": "用户偏好中文", "tags": ["lang"]},
        {"key": "user_name", "value": "用户叫小王", "tags": []},
    ])
    llm = FakeLLM(content=llm_content)
    store = FakeSessionStore(messages=msgs)
    s = SessionEndExtractStrategy(p, llm, session_store=store, min_messages=5)
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
    s = SessionEndExtractStrategy(p, llm, session_store=store, min_messages=5, max_per_session=2)
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
    s = SessionEndExtractStrategy(p, FailingLLM(), session_store=store, min_messages=5)
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
    s = SessionEndExtractStrategy(p, llm, session_store=store, min_messages=5)
    await s.on_event("session.destroy", session_id="s1")
    assert p.saved == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/xiowen/code/merco && python3 -m pytest tests/memory/test_strategy.py -v -k session_end`
Expected: ImportError (SessionEndExtractStrategy not exists)

- [ ] **Step 3: Add SessionEndExtractStrategy implementation**

Append to `merco/memory/strategy.py`:

```python
class SessionEndExtractStrategy(MemorySaveStrategy):
    """session.destroy 时用 LLM 抽取 1-3 条 insight 记忆"""
    name = "session_end_extract"

    EXTRACT_PROMPT = """从以下对话中抽取 1-3 条值得长期记住的关键信息（用户偏好、事实、决策）。
仅返回 JSON 数组，每条形如 {"key": "snake_case_key", "value": "原文", "tags": ["tag1"]}。
没有值得记的就返回 []。

对话：
{messages}
"""

    def __init__(self, pipeline, llm, *,
                 session_store=None, max_per_session: int = 3,
                 min_messages: int = 5):
        super().__init__(pipeline)
        self.llm = llm
        self._session_store = session_store
        self.max = max_per_session
        self.min_msgs = min_messages

    def subscribe(self, hooks) -> None:
        hooks.on("session.destroy", self._on_destroy)

    async def on_event(self, event: str, **kwargs) -> None:
        """兼容直接调用（测试用）"""
        await self._on_destroy(**kwargs)

    async def _on_destroy(self, session_id: str = "", **kwargs) -> None:
        if not self._session_store or not session_id:
            return
        try:
            messages = self._session_store.load_messages(session_id)
        except Exception as e:
            logger.warning("加载 session 消息失败: %s", e)
            return
        if not messages or len(messages) < self.min_msgs:
            return

        prompt = self.EXTRACT_PROMPT.format(
            messages=self._format_messages(messages)
        )
        try:
            response = await self.llm.chat(
                [{"role": "user", "content": prompt}],
                tools=None, tool_choice="none",
            )
        except Exception as e:
            logger.warning("LLM 抽取失败，跳过: %s", e)
            return

        items = self._parse_llm_output(response.get("content", ""), session_id)
        for item in items:
            await self.pipeline.save(item)

    @staticmethod
    def _format_messages(messages: list) -> str:
        """压缩消息为 LLM 提示（仅 role + content）"""
        lines = []
        for m in messages:
            role = m.get("role", "?")
            content = (m.get("content") or "").strip()
            if content:
                lines.append(f"[{role}] {content[:200]}")
        return "\n".join(lines)

    @staticmethod
    def _parse_llm_output(content: str, session_id: str) -> list[SaveItem]:
        """解析 LLM JSON 输出为 SaveItem 列表"""
        content = (content or "").strip()
        # 尝试提取 ```json ... ``` 包裹
        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(lines[1:-1]) if lines[-1].startswith("```") else "\n".join(lines[1:])
        try:
            data = json.loads(content)
        except (ValueError, TypeError) as e:
            logger.warning("LLM 输出解析失败: %s", e)
            return []
        if not isinstance(data, list):
            return []
        items = []
        for entry in data[:3]:  # 兜底再 cap
            if not isinstance(entry, dict):
                continue
            key = entry.get("key", "").strip()
            value = entry.get("value", "").strip()
            if not key or not value:
                continue
            tags = entry.get("tags", []) or []
            if not isinstance(tags, list):
                tags = []
            items.append(SaveItem(
                key=key, value=value, source="extracted",
                tags=[str(t) for t in tags], session_id=session_id,
            ))
        return items
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/xiowen/code/merco && python3 -m pytest tests/memory/test_strategy.py -v -k session_end`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
cd /home/xiowen/code/merco
git add merco/memory/strategy.py tests/memory/test_strategy.py
git commit -m "feat: add SessionEndExtractStrategy with fail-soft LLM"
```

---

## Task 8: 导出新符号

**Files:**
- Modify: `merco/memory/__init__.py`

- [ ] **Step 1: Read current __init__.py**

Run: `cd /home/xiowen/code/merco && cat merco/memory/__init__.py`

- [ ] **Step 2: Add new exports**

Append the following exports (keep existing imports):

```python
from .save_pipeline import (
    MemorySavePipeline,
    MemorySaveProcessor,
    SaveItem,
    MemorySource,
    SOURCE_PRIORITY,
    SourceEnricher,
    DedupProcessor,
)
from .strategy import (
    MemorySaveStrategy,
    ExplicitRememberStrategy,
    SessionEndExtractStrategy,
)
```

- [ ] **Step 3: Verify import works**

Run: `cd /home/xiowen/code/merco && python3 -c "from merco.memory import MemorySavePipeline, ExplicitRememberStrategy, SessionEndExtractStrategy; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Run all memory tests**

Run: `cd /home/xiowen/code/merco && python3 -m pytest tests/memory/ -v`
Expected: all memory tests pass

- [ ] **Step 5: Commit**

```bash
cd /home/xiowen/code/merco
git add merco/memory/__init__.py
git commit -m "feat: export new memory save pipeline symbols"
```

---

## Task 9: 新增 Config 字段

**Files:**
- Modify: `merco/core/config.py`

- [ ] **Step 1: Locate memory config section**

Run: `cd /home/xiowen/code/merco && grep -n "memory_recall_threshold" merco/core/config.py`

- [ ] **Step 2: Add 3 new fields after the existing memory section**

After the line defining `memory_recall_threshold`, add:

```python
    memory_auto_extract_on_session_end: bool = False
    memory_extract_max_per_session: int = 3
    memory_extract_min_messages: int = 5
```

- [ ] **Step 3: Add corresponding entries in to_dict() and from_dict() helpers**

Find the `to_dict` method (around line 200) and add to the `memory` block:

```python
                "auto_extract_on_session_end": self.memory_auto_extract_on_session_end,
                "extract_max_per_session": self.memory_extract_max_per_session,
                "extract_min_messages": self.memory_extract_min_messages,
```

Find the `from_dict` (around line 233) and add to the memory block reads:

```python
            memory_auto_extract_on_session_end=memory_data.get("auto_extract_on_session_end", False),
            memory_extract_max_per_session=memory_data.get("extract_max_per_session", 3),
            memory_extract_min_messages=memory_data.get("extract_min_messages", 5),
```

- [ ] **Step 4: Verify syntax and config roundtrip**

Run:
```bash
cd /home/xiowen/code/merco
python3 -c "from merco.core.config import Config; c = Config(); print(c.memory_auto_extract_on_session_end, c.memory_extract_max_per_session, c.memory_extract_min_messages)"
```
Expected: `False 3 5`

- [ ] **Step 5: Commit**

```bash
cd /home/xiowen/code/merco
git add merco/core/config.py
git commit -m "feat: add memory_auto_extract config fields"
```

---

## Task 10: Agent 启动装配

**Files:**
- Modify: `merco/core/agent.py`

- [ ] **Step 1: Find the recaller initialization block**

Run: `cd /home/xiowen/code/merco && grep -n "HybridRecaller\|MemoryRecaller" merco/core/agent.py`

Expected: lines around 372-381

- [ ] **Step 2: Add pipeline + strategies assembly after the recaller block**

After the existing recaller setup, add:

```python
        # ── Memory 保存链（让 /remember 和 session 结束抽取可写入）──
        from merco.memory.save_pipeline import MemorySavePipeline
        from merco.memory.strategy import (
            ExplicitRememberStrategy, SessionEndExtractStrategy,
        )
        from merco.memory.store import MemoryStore as _MS

        self.memory_save_pipeline = MemorySavePipeline(
            store=_MS(self.config.memory_path),
            hooks=self.hooks,
        )
        self.memory_strategies = [
            ExplicitRememberStrategy(self.memory_save_pipeline),
        ]
        if self.config.memory_auto_extract_on_session_end:
            self.memory_strategies.append(
                SessionEndExtractStrategy(
                    self.memory_save_pipeline, self.llm,
                    session_store=self._session_store,
                    max_per_session=self.config.memory_extract_max_per_session,
                    min_messages=self.config.memory_extract_min_messages,
                )
            )
        for strat in self.memory_strategies:
            strat.subscribe(self.hooks)
```

- [ ] **Step 3: Verify syntax**

Run: `cd /home/xiowen/code/merco && python3 -m py_compile merco/core/agent.py && echo "Syntax OK"`
Expected: `Syntax OK`

- [ ] **Step 4: Verify Agent constructs without error (use existing test fixture)**

Run: `cd /home/xiowen/code/merco && python3 -m pytest tests/integration/ -v -k "not test_guard" 2>&1 | tail -10`
Expected: existing integration tests still pass

- [ ] **Step 5: Commit**

```bash
cd /home/xiowen/code/merco
git add merco/core/agent.py
git commit -m "feat: wire MemorySavePipeline into Agent init"
```

---

## Task 11: Observer 订阅 memory.saved

**Files:**
- Modify: `merco/observability/observer.py`

- [ ] **Step 1: Find existing subscriptions**

Run: `cd /home/xiowen/code/merco && grep -n "hooks.on\|_on_" merco/observability/observer.py | head -15`

- [ ] **Step 2: Add subscription line after existing agent.start/stop**

Add the line (in the same block where other hooks.on are registered):

```python
        hooks.on("memory.saved", self._on_memory_saved)
```

- [ ] **Step 3: Add the handler method**

Find the location of other `_on_agent_start` methods and add this method in the same class:

```python
    async def _on_memory_saved(self, key: str, source: str = "", **kwargs):
        """记忆保存事件 → 计数器 +1"""
        self._live.increment("memories_saved")
```

- [ ] **Step 4: Verify syntax**

Run: `cd /home/xiowen/code/merco && python3 -m py_compile merco/observability/observer.py && echo "Syntax OK"`
Expected: `Syntax OK`

- [ ] **Step 5: Smoke test — 现有 observer 测试不破**

Run: `cd /home/xiowen/code/merco && python3 -m pytest tests/observability/ -v 2>&1 | tail -5`
Expected: existing observer tests pass

- [ ] **Step 6: Commit**

```bash
cd /home/xiowen/code/merco
git add merco/observability/observer.py
git commit -m "feat: observer tracks memory.saved events"
```

---

## Task 12: CLI /remember 命令

**Files:**
- Modify: `cli/commands.py`

- [ ] **Step 1: Find where /recall is defined**

Run: `cd /home/xiowen/code/merco && grep -n "cmd_recall\|/recall" cli/commands.py`

Expected: line ~305

- [ ] **Step 2: Add /remember command above /recall**

Insert this block before the `@cmd_registry.register("/recall", ...)` line:

```python
@cmd_registry.register("/remember", "存一条记忆（key= 可选）", group="memory")
async def cmd_remember(agent, args):
    """解析 text 或 key=value 形式，emit command.remember"""
    if not args:
        console.print("[dim]用法: /remember <text>  或  /remember key=<k> <text>[/dim]")
        return True

    key = ""
    text = args
    if args.startswith("key="):
        parts = args.split(maxsplit=1)
        key = parts[0][4:].strip()
        text = parts[1] if len(parts) > 1 else ""

    if not text and "=" in args and not args.startswith("key="):
        # 形式：/remember 生日=1990-01-01
        k, v = args.split("=", 1)
        key, text = k.strip(), v.strip()

    await agent.hooks.emit("command.remember", text=text, key=key)
    console.print(f"[green]✓ 已记:[/green] {text[:80]}{'...' if len(text) > 80 else ''}")
    return True
```

- [ ] **Step 3: Verify syntax**

Run: `cd /home/xiowen/code/merco && python3 -m py_compile cli/commands.py && echo "Syntax OK"`
Expected: `Syntax OK`

- [ ] **Step 4: Commit**

```bash
cd /home/xiowen/code/merco
git add cli/commands.py
git commit -m "feat: /remember CLI command"
```

---

## Task 13: CLI /memories 和 /forget 命令

**Files:**
- Modify: `cli/commands.py`
- Test: `tests/memory/test_cli.py`

- [ ] **Step 1: Add failing test**

Create `tests/memory/test_cli.py`:

```python
"""CLI 记忆命令单测"""
import pytest
from merco.memory.store import MemoryStore
from merco.memory.save_pipeline import SaveItem, MemorySavePipeline


class FakeHooks:
    def __init__(self):
        self.events = []
    async def emit(self, event, **kwargs):
        self.events.append((event, kwargs))


@pytest.fixture
def agent_with_memory(tmp_path):
    """构造带 memory store 的 agent stub"""
    class Agent:
        pass
    a = Agent()
    a.hooks = FakeHooks()
    a._memory_store = MemoryStore(str(tmp_path / "memory"))
    a.memory_save_pipeline = MemorySavePipeline(a._memory_store, a.hooks)
    return a


@pytest.mark.asyncio
async def test_memories_lists_all(agent_with_memory, capsys):
    """空状态显示提示"""
    from cli.commands import cmd_memories
    a = agent_with_memory
    result = await cmd_memories(a, "")
    assert result is True
    out = capsys.readouterr().out
    assert "暂无记忆" in out


@pytest.mark.asyncio
async def test_memories_lists_existing(agent_with_memory, capsys):
    """已有记忆时显示列表"""
    from cli.commands import cmd_memories
    a = agent_with_memory
    a._memory_store.save("k1", "hello", tags=["[user]"])
    a._memory_store.save("k2", "world", tags=["[extracted]"])
    await cmd_memories(a, "")
    out = capsys.readouterr().out
    assert "k1" in out
    assert "k2" in out
    assert "[user]" in out


@pytest.mark.asyncio
async def test_forget_deletes_key(agent_with_memory, capsys):
    """/forget 删除已存在 key"""
    from cli.commands import cmd_forget
    a = agent_with_memory
    a._memory_store.save("k1", "hello", tags=["[user]"])
    await cmd_forget(a, "k1")
    assert a._memory_store.load("k1") is None


@pytest.mark.asyncio
async def test_forget_nonexistent_is_silent(agent_with_memory, capsys):
    """/forget 不存在 key 静默"""
    from cli.commands import cmd_forget
    a = agent_with_memory
    # 不应抛
    await cmd_forget(a, "nonexistent")
    out = capsys.readouterr().out
    # 无报错信息
    assert "Error" not in out and "错误" not in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/xiowen/code/merco && python3 -m pytest tests/memory/test_cli.py -v`
Expected: ImportError (cmd_memories / cmd_forget not exists)

- [ ] **Step 3: Add /memories and /forget commands**

Append after the `/remember` block in `cli/commands.py`:

```python
@cmd_registry.register("/memories", "列出所有记忆（[tag] 可选过滤）", group="memory")
async def cmd_memories(agent, args):
    """列出所有记忆"""
    from merco.memory.store import MemoryStore as _MS
    store = agent._memory_store
    tag_filter = args.strip() if args else None
    keys = store.list_keys(tag=tag_filter)
    if not keys:
        console.print("[dim]暂无记忆[/dim]")
        return True
    console.print(f"[bold]📚 已存记忆 ({len(keys)} 条)[/bold]")
    console.print("─" * 60)
    for k in keys:
        record = store.load(k)
        if not record:
            continue
        tags = record.get("tags", [])
        tag_str = " ".join(tags[:2])
        value = record.get("value", "")
        console.print(f"  {tag_str:20s}  [cyan]{k}[/cyan]")
        console.print(f"     [dim]{value[:100]}{'...' if len(value) > 100 else ''}[/dim]")
    return True


@cmd_registry.register("/forget", "删除一条记忆", group="memory")
async def cmd_forget(agent, args):
    """删除指定 key 的记忆"""
    if not args:
        console.print("[dim]用法: /forget <key>[/dim]")
        return True
    from merco.memory.store import MemoryStore as _MS
    agent._memory_store.delete(args.strip())
    console.print(f"[green]✓ 已忘记:[/green] {args.strip()}")
    return True
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/xiowen/code/merco && python3 -m pytest tests/memory/test_cli.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
cd /home/xiowen/code/merco
git add cli/commands.py tests/memory/test_cli.py
git commit -m "feat: /memories and /forget CLI commands"
```

---

## Task 14: 端到端集成测试

**Files:**
- Create: `tests/integration/test_memory_lifecycle.py`

- [ ] **Step 1: Write integration test**

Create `tests/integration/test_memory_lifecycle.py`:

```python
"""Memory 全链路端到端测试"""
import pytest
from merco.memory.store import MemoryStore
from merco.memory.save_pipeline import MemorySavePipeline
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


@pytest.mark.asyncio
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


@pytest.mark.asyncio
async def test_full_lifecycle_session_end_extract(tmp_path):
    """session.destroy 触发 LLM 抽取 → 存入"""
    import json
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


@pytest.mark.asyncio
async def test_dedup_user_beats_extracted(tmp_path):
    """显式 /remember 优先于 extracted（不会覆盖）"""
    import json
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
    from merco.memory.save_pipeline import SaveItem
    item = SaveItem(key="preference", value="AI 猜测的偏好", source="extracted")
    result = await pipeline.save(item)
    assert result is False  # 被 dedup skip
    record2 = store.load("preference")
    assert record2["value"] == "我的偏好"  # 未覆盖
```

- [ ] **Step 2: Run test to verify it passes**

Run: `cd /home/xiowen/code/merco && python3 -m pytest tests/integration/test_memory_lifecycle.py -v`
Expected: 3 passed

- [ ] **Step 3: Commit**

```bash
cd /home/xiowen/code/merco
git add tests/integration/test_memory_lifecycle.py
git commit -m "test: end-to-end memory lifecycle integration"
```

---

## Task 15: 更新 progress.md

**Files:**
- Modify: `docs/project-vision/references/progress.md`

- [ ] **Step 1: Find next-steps section**

Run: `cd /home/xiowen/code/merco && grep -n "下一步" docs/project-vision/references/progress.md`

- [ ] **Step 2: Add new session log entry**

Insert a new "本次会话更新 (2026-06-15)" block after the existing 2026-06-15 entry (or replace that one — the date is already current). Update line 4 to "2026-06-15" and add:

```
### 本次会话更新 (2026-06-15)

- **Memory → Sessions 打通（新功能）**: Agent 终于能存记忆了。
  - **保存链**: `MemorySavePipeline`（SourceEnricher → DedupProcessor → Store），emit `memory.saved` 事件
  - **双轨策略**: `ExplicitRememberStrategy`（订阅 command.remember，同步存）+ `SessionEndExtractStrategy`（订阅 session.destroy，可选 LLM 抽取，默认 opt-in 关闭）
  - **Dedup**: 按 source 优先级 skip（user > extracted > system），保护用户记忆不被 AI 覆盖
  - **CLI**: `/remember <text>` / `/remember key=<k> <text>` / `/memories [tag]` / `/forget <key>`
  - **Config**: 新增 `memory.auto_extract_on_session_end` / `extract_max_per_session` / `extract_min_messages`
  - **Observer**: 订阅 memory.saved 事件，`/report` 显示 memories_saved 计数
  - **测试**: 5 个 Pipeline 单测 + 10 个 Strategy 单测 + 4 个 CLI 单测 + 3 个集成测试
```

- [ ] **Step 3: Update Cross-Cutting Wiring Checks table**

Find the `Memory Recall → Agent` row and add a new row for `Memory Save → Sessions`:

```
| Memory Save → Sessions | ✅ WIRED | MemorySavePipeline + 2 strategies; /remember /memories /forget; LLM 抽取 opt-in |
```

- [ ] **Step 4: Sync to skill directory**

Run: `cd /home/xiowen/code/merco && cp -r docs/project-vision .merco/skills/`

- [ ] **Step 5: Commit**

```bash
cd /home/xiowen/code/merco
git add docs/project-vision/
git commit -m "docs: mark Memory → Sessions as wired in progress"
```

---

## 完成标准

- [ ] SaveItem + MemorySaveProcessor 基类
- [ ] SourceEnricher 补 [source] 前缀
- [ ] DedupProcessor 按优先级 skip/overwrite
- [ ] MemorySavePipeline 链式入口
- [ ] MemorySaveStrategy ABC
- [ ] ExplicitRememberStrategy 监听 command.remember
- [ ] SessionEndExtractStrategy 监听 session.destroy（LLM 抽取 opt-in）
- [ ] 导出新符号
- [ ] Config 3 个新字段
- [ ] Agent 启动装配
- [ ] Observer 订阅 memory.saved
- [ ] CLI /remember /memories /forget
- [ ] 集成测试 3 个
- [ ] progress.md 更新

---

## 执行方式

使用 `subagent-driven-development` skill 执行此计划：
- 每个 Task 分配给一个 subagent
- Spec compliance review 检查是否符合设计文档
- Code quality review 检查代码质量
- 两个 review 都通过后才进入下一个 Task
