# Memory Recall 实现计划

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** 自动从历史会话中召回相关内容，注入 Agent 上下文。

**Architecture:** `BaseRecaller` ABC → `FTS5Recaller`（调 SessionSearch）+ `MemoryRecaller`（调 MemoryStore）→ `HybridRecaller` 聚合后注入 `_build_system_prompt()` 末尾。配置项走 `MercoConfig`。

**Tech Stack:** Python 3.12+, SQLite FTS5, asyncio, ABC

---

### Task 1: 重写 memory/recall.py — Recaller 接口和协议

**Objective:** 定义 `RecallResult` dataclass + `BaseRecaller` ABC + `FTS5Recaller` + `MemoryRecaller` + `HybridRecaller`

**Files:**
- Modify: `merco/memory/recall.py`
- Modify: `merco/memory/__init__.py`

**Step 1: 写测试**

```python
# tests/memory/test_recall.py
import pytest
from merco.memory.recall import RecallResult, BaseRecaller, FTS5Recaller, MemoryRecaller, HybridRecaller

class TestRecallResult:
    def test_defaults(self):
        r = RecallResult(snippet="hello", session_title="test", score=0.5, source="fts5")
        assert r.snippet == "hello"
        assert r.source == "fts5"

class TestFTS5Recaller:
    @pytest.mark.asyncio
    async def test_recall_empty(self):
        # FTS5Recaller 需要 SessionSearch 实例，用 mock
        ...

class TestHybridRecaller:
    @pytest.mark.asyncio
    async def test_merge_and_dedup(self):
        ...
```

**Step 2: 运行测试，确认失败**

```bash
pytest tests/memory/test_recall.py -v
```
Expected: FAIL — module not found / classes not defined

**Step 3: 写实现 — `merco/memory/recall.py`**

```python
"""记忆召回 — 从历史会话和持久化记忆中检索相关内容"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

logger = logging.getLogger("merco.recall")


@dataclass
class RecallResult:
    """召回结果"""
    snippet: str           # 截断后的文本
    session_title: str     # 来源会话标题
    score: float           # 匹配分数（FTS5 rank 或 embedding cosine）
    source: str            # "fts5" | "memory"


class BaseRecaller(ABC):
    """召回策略基类"""
    name: str = ""

    @abstractmethod
    async def recall(self, query: str, limit: int) -> list[RecallResult]:
        """搜索并返回召回结果"""
        ...


class FTS5Recaller(BaseRecaller):
    """基于 SessionSearch FTS5 索引的召回"""

    name = "fts5"

    def __init__(self, session_search):
        self._search = session_search  # SessionSearch 实例

    async def recall(self, query: str, limit: int) -> list[RecallResult]:
        results = self._search.search(query, limit=limit)
        return [
            RecallResult(
                snippet=r.get("snippet", ""),
                session_title=r.get("session_title", ""),
                score=float(i + 1),  # rank 越大越靠前
                source="fts5",
            )
            for i, r in enumerate(results)
        ]


class MemoryRecaller(BaseRecaller):
    """基于 MemoryStore JSON 文件搜索的召回"""

    name = "memory"

    def __init__(self, memory_store):
        self._store = memory_store  # MemoryStore 实例

    async def recall(self, query: str, limit: int) -> list[RecallResult]:
        results = self._store.search(query)
        return [
            RecallResult(
                snippet=str(m.get("value", "")),
                session_title=m.get("key", "memory"),
                score=1.0,
                source="memory",
            )
            for m in results[:limit]
        ]


class HybridRecaller(BaseRecaller):
    """聚合多个 Recaller，统一排序去重截断"""

    name = "hybrid"

    def __init__(self, recallers: list[BaseRecaller] | None = None,
                 limit: int = 3, max_chars: int = 300):
        self._recallers = recallers or []
        self._limit = limit
        self._max_chars = max_chars
        self._cache: dict[str, list[RecallResult]] = {}

    def add(self, recaller: BaseRecaller) -> "HybridRecaller":
        self._recallers.append(recaller)
        return self

    async def recall(self, query: str, limit: int | None = None) -> list[RecallResult]:
        limit = limit or self._limit

        # 缓存：同一 query 不重复查询
        cache_key = f"{query}:{limit}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        all_results: list[RecallResult] = []
        for r in self._recallers:
            try:
                results = await r.recall(query, limit)
                all_results.extend(results)
            except Exception:
                logger.debug("Recaller '%s' 异常", r.name, exc_info=True)

        # 按 score 降序
        all_results.sort(key=lambda x: x.score, reverse=True)

        # 去重：相同 snippet 只保留第一条
        seen = set()
        unique: list[RecallResult] = []
        for r in all_results:
            key = r.snippet[:80]
            if key not in seen:
                seen.add(key)
                unique.append(r)

        # 截断
        for r in unique:
            if len(r.snippet) > self._max_chars:
                r.snippet = r.snippet[:self._max_chars] + "..."

        result = unique[:limit]
        self._cache[cache_key] = result
        return result
```

**Step 4: 运行测试，确认通过**

```bash
pytest tests/memory/test_recall.py -v
```
Expected: PASS

**Step 5: 更新 `__init__.py`**

```python
# merco/memory/__init__.py
from .store import MemoryStore
from .recall import MemoryRecall, RecallResult, BaseRecaller, FTS5Recaller, MemoryRecaller, HybridRecaller

__all__ = ["MemoryStore", "MemoryRecall", "RecallResult", "BaseRecaller",
           "FTS5Recaller", "MemoryRecaller", "HybridRecaller"]
```

**Step 6: Commit**

```bash
git add merco/memory/recall.py merco/memory/__init__.py tests/memory/test_recall.py
git commit -m "feat: memory recall interface with FTS5 + MemoryStore recallers"
```

---

### Task 2: MercoConfig 加 memory 配置段

**Objective:** 在 `MercoConfig` 和 `merco.json` 中新增 `memory` 子配置

**Files:**
- Modify: `merco/core/config.py`

**Step 1: 写测试**

```python
# tests/core/test_config.py (追加)
def test_memory_config_defaults():
    cfg = MercoConfig()
    assert cfg.memory_recall_enabled is True
    assert cfg.memory_recall_limit == 3
    assert cfg.memory_recall_max_chars == 300
    assert cfg.memory_recall_threshold == 0.0

def test_memory_config_from_dict():
    cfg = MercoConfig._from_dict({
        "memory": {
            "recall_enabled": False,
            "recall_limit": 5,
            "recall_max_chars": 500,
            "recall_threshold": 0.5,
        }
    })
    assert cfg.memory_recall_enabled is False
    assert cfg.memory_recall_limit == 5
```

**Step 2: 运行测试，确认失败**

```bash
pytest tests/core/test_config.py::test_memory_config_defaults -v
```
Expected: FAIL — AttributeError

**Step 3: 写实现**

在 `MercoConfig` dataclass 加 4 个字段：

```python
@dataclass
class MercoConfig:
    # ... existing fields ...
    memory_recall_enabled: bool = True
    memory_recall_limit: int = 3
    memory_recall_max_chars: int = 300
    memory_recall_threshold: float = 0.0
```

同步更新 `_to_dict()` 和 `_from_dict()`：

```python
def _to_dict(self) -> dict:
    return {
        # ... existing keys ...
        "memory": {
            "recall_enabled": self.memory_recall_enabled,
            "recall_limit": self.memory_recall_limit,
            "recall_max_chars": self.memory_recall_max_chars,
            "recall_threshold": self.memory_recall_threshold,
        },
    }

@classmethod
def _from_dict(cls, data: dict) -> "MercoConfig":
    mem = data.get("memory", {})
    return cls(
        # ... existing fields ...
        memory_recall_enabled=mem.get("recall_enabled", True),
        memory_recall_limit=mem.get("recall_limit", 3),
        memory_recall_max_chars=mem.get("recall_max_chars", 300),
        memory_recall_threshold=mem.get("recall_threshold", 0.0),
    )
```

**Step 4: 运行测试，确认通过**

```bash
pytest tests/core/test_config.py -v
```

**Step 5: Commit**

```bash
git add merco/core/config.py tests/core/test_config.py
git commit -m "feat: add memory recall config options"
```

---

### Task 3: Agent 集成 — `_build_system_prompt` 注入召回

**Objective:** Agent 初始化 `HybridRecaller`，在 `_build_system_prompt()` 末尾注入召回结果

**Files:**
- Modify: `merco/core/agent.py`

**Step 1: 写测试**

```python
# tests/core/test_agent.py (追加)
@pytest.mark.asyncio
async def test_build_system_prompt_with_recall(agent):
    agent.config.memory_recall_enabled = True
    agent._current_prompt = "test query"
    # mock recaller
    from merco.memory.recall import RecallResult
    agent.recaller._cache = {}
    agent.recaller._recallers = []
    
    class MockRecaller:
        name = "mock"
        async def recall(self, query, limit):
            return [RecallResult("snippet1", "session1", 1.0, "fts5")]
    agent.recaller.add(MockRecaller())
    
    prompt = await agent._build_system_prompt()
    assert "相关历史对话" in prompt
    assert "snippet1" in prompt

@pytest.mark.asyncio
async def test_recall_disabled_no_injection(agent):
    agent.config.memory_recall_enabled = False
    agent._current_prompt = "test"
    agent.recaller._recallers = []
    prompt = await agent._build_system_prompt()
    assert "相关历史对话" not in prompt
```

**Step 2: 运行测试，确认失败**

```bash
pytest tests/core/test_agent.py::test_build_system_prompt_with_recall -v
```

**Step 3: 写实现**

在 `Agent.__init__` 末尾加：

```python
# ── Memory 召回 ──
from merco.memory.recall import HybridRecaller, FTS5Recaller, MemoryRecaller
from merco.memory.store import MemoryStore

_fts5 = FTS5Recaller(self._search)
_mem = MemoryRecaller(MemoryStore(config.memory_path))
self.recaller = HybridRecaller(
    recallers=[_fts5, _mem],
    limit=config.memory_recall_limit,
    max_chars=config.memory_recall_max_chars,
)
```

`_build_system_prompt` 改为 async，末尾加注入：

```python
async def _build_system_prompt(self) -> str:
    base = self.prompt_builder.build(self)
    
    if self.config.memory_recall_enabled and self._current_prompt:
        try:
            recalled = await self.recaller.recall(self._current_prompt)
            if recalled:
                lines = ["\n## 相关历史对话（仅供参考）"]
                for i, r in enumerate(recalled, 1):
                    lines.append(f"{i}. [{r.session_title}] {r.snippet}")
                base += "\n".join(lines)
        except Exception:
            logger.debug("Memory recall failed", exc_info=True)
    
    return base
```

**Step 4: 运行测试，确认通过**

```bash
pytest tests/core/test_agent.py -v
```

**Step 5: Commit**

```bash
git add merco/core/agent.py tests/core/test_agent.py
git commit -m "feat: inject memory recall into system prompt"
```

---

### Task 4: `/recall` CLI 命令

**Objective:** 手动触发召回，预览结果

**Files:**
- Modify: `cli/main.py`

**Step 1: 在 `handle_command()` 加分支**

```python
elif command == "/recall":
    query = parts[1] if len(parts) > 1 else ""
    if not query:
        console.print("[dim]用法: /recall <关键词>[/dim]")
        return True
    recalled = await agent.recaller.recall(query)
    if not recalled:
        console.print("[dim]未找到相关历史[/dim]")
    else:
        console.print(f"[bold]🔍 '{query}' 召回结果:[/bold]")
        for i, r in enumerate(recalled, 1):
            console.print(f"  {i}. [{r.session_title}] [dim]({r.source}, {r.score:.1f})[/dim]")
            console.print(f"     [bright_black]{r.snippet}[/bright_black]")
    return True
```

**Step 2: 同步更新 `/help` 列表**

在 `/help` 输出的命令列表中加入 `/recall` 条目。

**Step 3: 验证**

```bash
# 启动 merco，键入 /recall memory
# Expected: FTS5 搜索结果列表
```

**Step 4: Commit**

```bash
git add cli/main.py
git commit -m "feat: add /recall CLI command"
```

---

## Task Order

```
Task 1: recall.py 接口     ← 无依赖
Task 2: config.py 配置     ← 无依赖
Task 3: agent.py 集成      ← 依赖 Task 1 + 2
Task 4: CLI /recall        ← 依赖 Task 1 + 3
```
