# merco MemoryBackend 插件化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 MemoryStore 从单一 JSON 后端改为可拔插的 MemoryBackend 架构

**Architecture:** MemoryBackend ABC + JSONBackend（迁移现有逻辑）+ MemoryStore facade（委托给 backend）+ MemoryBackendRegistry + PluginContext 扩展

**Tech Stack:** Python 3.12, ABC, dataclass

---

## 文件结构

| 文件 | 职责 |
|------|------|
| `merco/memory/backend.py` | MemoryBackend ABC + MemoryBackendRegistry |
| `merco/memory/backends/__init__.py` | 后端包 |
| `merco/memory/backends/json_backend.py` | JSONBackend（迁移自 MemoryStore） |
| `merco/memory/store.py` | MemoryStore facade（委托给 backend） |
| `merco/plugins/base.py` | PluginContext 新增 memory_backends |
| `merco/core/config.py` | memory.backend 配置字段 |
| `merco/core/agent.py` | 装配 registry + 选 backend |
| `tests/memory/test_backend.py` | MemoryBackend + JSONBackend + Registry 单测 |
| `tests/memory/test_backend_integration.py` | 向后兼容集成测试 |

---

## Task 1: MemoryBackend ABC + MemoryBackendRegistry

**Files:**
- Create: `merco/memory/backend.py`
- Test: `tests/memory/test_backend.py`

- [ ] **Step 1: Write the failing test**

Create `tests/memory/test_backend.py`:

```python
"""MemoryBackend + Registry 单测"""
import pytest
from merco.memory.backend import MemoryBackend, MemoryBackendRegistry


class DummyBackend(MemoryBackend):
    name = "dummy"

    def __init__(self):
        self._data: dict[str, dict] = {}

    def save(self, key, value, tags=None):
        self._data[key] = {"key": key, "value": value, "tags": tags or []}

    def load(self, key):
        return self._data.get(key)

    def delete(self, key):
        self._data.pop(key, None)

    def list_keys(self, tag=None):
        if tag:
            return [k for k, v in self._data.items() if tag in v.get("tags", [])]
        return list(self._data.keys())

    def search(self, query):
        results = []
        for v in self._data.values():
            if query.lower() in str(v).lower():
                results.append(v)
        return results


class TestMemoryBackendABC:
    def test_cannot_instantiate_abstract(self):
        with pytest.raises(TypeError):
            MemoryBackend()  # noqa

    def test_concrete_subclass_works(self):
        b = DummyBackend()
        b.save("k1", "v1")
        assert b.load("k1")["value"] == "v1"


class TestMemoryBackendRegistry:
    def test_register_and_get(self):
        reg = MemoryBackendRegistry()
        reg.register(DummyBackend())
        assert reg.get("dummy") is not None
        assert reg.get("nonexistent") is None

    def test_list(self):
        reg = MemoryBackendRegistry()
        reg.register(DummyBackend())
        assert len(reg.list()) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/xiowen/code/merco && python3 -m pytest tests/memory/test_backend.py -v`
Expected: ImportError

- [ ] **Step 3: Implement MemoryBackend ABC + Registry**

Create `merco/memory/backend.py`:

```python
"""MemoryBackend ABC + MemoryBackendRegistry"""
from __future__ import annotations

from abc import ABC, abstractmethod


class MemoryBackend(ABC):
    """记忆存储后端基类"""
    name: str = ""

    @abstractmethod
    def save(self, key: str, value, tags: list = None) -> None:
        """保存记忆"""
        ...

    @abstractmethod
    def load(self, key: str) -> dict | None:
        """加载记忆"""
        ...

    @abstractmethod
    def delete(self, key: str) -> None:
        """删除记忆"""
        ...

    @abstractmethod
    def list_keys(self, tag: str = None) -> list[str]:
        """列出所有记忆键"""
        ...

    @abstractmethod
    def search(self, query: str) -> list[dict]:
        """搜索记忆"""
        ...


class MemoryBackendRegistry:
    """MemoryBackend 注册表"""

    def __init__(self):
        self._backends: dict[str, MemoryBackend] = {}

    def register(self, backend: MemoryBackend) -> None:
        self._backends[backend.name] = backend

    def get(self, name: str) -> MemoryBackend | None:
        return self._backends.get(name)

    def list(self) -> list[MemoryBackend]:
        return list(self._backends.values())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/xiowen/code/merco && python3 -m pytest tests/memory/test_backend.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
cd /home/xiowen/code/merco
git add merco/memory/backend.py tests/memory/test_backend.py
git commit -m "feat: add MemoryBackend ABC and MemoryBackendRegistry"
```

---

## Task 2: JSONBackend（迁移自 MemoryStore）

**Files:**
- Create: `merco/memory/backends/__init__.py`
- Create: `merco/memory/backends/json_backend.py`
- Test: `tests/memory/test_backend.py` (append)

- [ ] **Step 1: Append test to test_backend.py**

```python
from merco.memory.backends.json_backend import JSONBackend


class TestJSONBackend:
    def test_save_and_load(self, tmp_path):
        b = JSONBackend(str(tmp_path))
        b.save("k1", {"text": "hello"}, tags=["[user]"])
        record = b.load("k1")
        assert record["value"]["text"] == "hello"
        assert "[user]" in record["tags"]

    def test_delete(self, tmp_path):
        b = JSONBackend(str(tmp_path))
        b.save("k1", "v1")
        b.delete("k1")
        assert b.load("k1") is None

    def test_list_keys(self, tmp_path):
        b = JSONBackend(str(tmp_path))
        b.save("k1", "v1", tags=["[user]"])
        b.save("k2", "v2", tags=["[extracted]"])
        keys = b.list_keys()
        assert len(keys) == 2
        assert len(b.list_keys(tag="[user]")) == 1

    def test_search(self, tmp_path):
        b = JSONBackend(str(tmp_path))
        b.save("k1", {"text": "hello world"})
        b.save("k2", {"text": "goodbye"})
        results = b.search("hello")
        assert len(results) == 1
        assert results[0]["key"] == "k1"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/xiowen/code/merco && python3 -m pytest tests/memory/test_backend.py -v -k JSON`
Expected: ImportError

- [ ] **Step 3: Implement JSONBackend**

Create `merco/memory/backends/__init__.py`:

```python
"""记忆后端实现"""

from .json_backend import JSONBackend

__all__ = ["JSONBackend"]
```

Create `merco/memory/backends/json_backend.py`:

```python
"""JSONBackend — 每记忆一个 .json 文件"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from merco.memory.backend import MemoryBackend


class JSONBackend(MemoryBackend):
    """JSON 文件后端"""
    name = "json"

    def __init__(self, base_path: str):
        self.base_path = Path(base_path).expanduser()
        self.base_path.mkdir(parents=True, exist_ok=True)

    def save(self, key: str, value, tags: list = None) -> None:
        entry = {
            "key": key,
            "value": value,
            "tags": tags or [],
            "created_at": datetime.now().isoformat(),
        }
        file_path = self.base_path / f"{key}.json"
        with open(file_path, "w") as f:
            json.dump(entry, f, indent=2)

    def load(self, key: str) -> dict | None:
        file_path = self.base_path / f"{key}.json"
        if not file_path.exists():
            return None
        with open(file_path) as f:
            return json.load(f)

    def delete(self, key: str) -> None:
        file_path = self.base_path / f"{key}.json"
        if file_path.exists():
            file_path.unlink()

    def list_keys(self, tag: str = None) -> list[str]:
        keys = []
        for f in self.base_path.glob("*.json"):
            if tag:
                with open(f) as fh:
                    data = json.load(fh)
                    if tag in data.get("tags", []):
                        keys.append(f.stem)
            else:
                keys.append(f.stem)
        return keys

    def search(self, query: str) -> list[dict]:
        results = []
        query_lower = query.lower()
        for f in self.base_path.glob("*.json"):
            with open(f) as fh:
                data = json.load(fh)
                content = json.dumps(data).lower()
                if query_lower in content:
                    results.append(data)
        return results
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/xiowen/code/merco && python3 -m pytest tests/memory/test_backend.py -v`
Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
cd /home/xiowen/code/merco
git add merco/memory/backends/ tests/memory/test_backend.py
git commit -m "feat: add JSONBackend (migrated from MemoryStore)"
```

---

## Task 3: MemoryStore facade

**Files:**
- Modify: `merco/memory/store.py`

- [ ] **Step 1: Rewrite MemoryStore as facade**

Replace `merco/memory/store.py` with:

```python
"""记忆存储引擎 — facade，委托给 MemoryBackend"""
from __future__ import annotations

from typing import Optional
from .backend import MemoryBackend
from .backends.json_backend import JSONBackend


class MemoryStore:
    """持久化记忆存储"""

    def __init__(self, base_path: str = None, backend: MemoryBackend = None):
        if backend:
            self.backend = backend
        else:
            self.backend = JSONBackend(base_path or "~/.merco/memory")

    def save(self, key: str, value, tags: list = None):
        return self.backend.save(key, value, tags)

    def load(self, key: str) -> Optional[dict]:
        return self.backend.load(key)

    def delete(self, key: str):
        return self.backend.delete(key)

    def list_keys(self, tag: str = None) -> list[str]:
        return self.backend.list_keys(tag)

    def search(self, query: str) -> list[dict]:
        return self.backend.search(query)
```

- [ ] **Step 2: Run existing memory tests to verify backward compatibility**

Run: `cd /home/xiowen/code/merco && python3 -m pytest tests/memory/test_save_pipeline.py tests/memory/test_recall.py tests/memory/test_strategy.py tests/memory/test_cli.py -v 2>&1 | tail -10`

- [ ] **Step 3: Commit**

```bash
cd /home/xiowen/code/merco
git add merco/memory/store.py
git commit -m "feat: MemoryStore as facade delegating to MemoryBackend"
```

---

## Task 4: PluginContext 扩展 + Config + Agent 装配

**Files:**
- Modify: `merco/plugins/base.py`
- Modify: `merco/core/config.py`
- Modify: `merco/core/agent.py`

- [ ] **Step 1: Add memory_backends to PluginContext**

In `merco/plugins/base.py`:

```python
from merco.memory.backend import MemoryBackendRegistry
```

Add parameter: `memory_backends: "MemoryBackendRegistry" = None,`

Store: `self.memory_backends = memory_backends`

- [ ] **Step 2: Add memory.backend config field**

In `merco/core/config.py`, add to MercoConfig:

```python
memory_backend: str = "json"
```

Add to `_to_dict` memory block:

```python
"backend": self.memory_backend,
```

Add to `_from_dict` memory block read:

```python
memory_backend=memory_data.get("backend", "json"),
```

- [ ] **Step 3: Wire to Agent**

In `merco/core/agent.py`, replace the MemoryStore creation block with:

```python
        # ── Memory 召回 ──
        from merco.memory.recall import HybridRecaller, FTS5Recaller, MemoryRecaller
        from merco.memory.store import MemoryStore
        from merco.memory.backend import MemoryBackendRegistry
        from merco.memory.backends.json_backend import JSONBackend

        self.memory_backends = MemoryBackendRegistry()
        self.memory_backends.register(JSONBackend(config.memory_path))

        backend_name = config.memory_backend or "json"
        selected_backend = self.memory_backends.get(backend_name) or self.memory_backends.get("json")

        _fts5 = FTS5Recaller(self._search)
        _mem = MemoryRecaller(MemoryStore(backend=selected_backend))
        self.recaller = (
            HybridRecaller(limit=config.memory_recall_limit, max_chars=config.memory_recall_max_chars)
            .add(_fts5)
            .add(_mem)
        )

        # ── Memory 保存链 ──
        ...
        self._memory_store = MemoryStore(backend=selected_backend)
        self.memory_save_pipeline = MemorySavePipeline(
            store=self._memory_store,
            hooks=self.hooks,
        )
        ...

        # ── 注入 PluginContext ──
        self._plugin_ctx.memory_backends = self.memory_backends
```

- [ ] **Step 4: Verify syntax + run tests**

Run: `cd /home/xiowen/code/merco && python3 -m py_compile merco/plugins/base.py && python3 -m py_compile merco/core/config.py && python3 -m py_compile merco/core/agent.py && echo "Syntax OK"`

Run: `cd /home/xiowen/code/merco && python3 -m pytest tests/memory/ tests/plugins/ tests/unit/test_config.py -v`

- [ ] **Step 5: Commit**

```bash
cd /home/xiowen/code/merco
git add merco/plugins/base.py merco/core/config.py merco/core/agent.py
git commit -m "feat: wire MemoryBackendRegistry into PluginContext and Agent"
```

---

## Task 5: 向后兼容集成测试

**Files:**
- Create: `tests/memory/test_backend_integration.py`

- [ ] **Step 1: Write backward compatibility test**

Create `tests/memory/test_backend_integration.py`:

```python
"""MemoryBackend 向后兼容集成测试"""
import pytest
from merco.memory.store import MemoryStore
from merco.memory.backends.json_backend import JSONBackend


def test_memory_store_no_backend_uses_json_default(tmp_path):
    """MemoryStore() 无 backend 参数 → 自动用 JSONBackend"""
    store = MemoryStore(str(tmp_path / "memory"))
    store.save("k1", "hello")
    assert store.load("k1")["value"] == "hello"


def test_memory_store_with_explicit_backend(tmp_path):
    """MemoryStore(backend=JSONBackend(...)) 委托正确"""
    backend = JSONBackend(str(tmp_path / "custom"))
    store = MemoryStore(backend=backend)
    store.save("k1", "v1")
    assert store.load("k1") is not None
    # 验证文件在 custom 目录下
    import os
    assert os.path.exists(str(tmp_path / "custom" / "k1.json"))


def test_memory_store_full_crud(tmp_path):
    """MemoryStore facade CRUD 完整"""
    store = MemoryStore(str(tmp_path / "memory"))
    # create
    store.save("k1", "v1", tags=["[user]"])
    # read
    assert store.load("k1") is not None
    # list
    assert "k1" in store.list_keys()
    assert "k1" in store.list_keys(tag="[user]")
    # search
    results = store.search("v1")
    assert len(results) == 1
    # delete
    store.delete("k1")
    assert store.load("k1") is None
```

- [ ] **Step 2: Run test**

Run: `cd /home/xiowen/code/merco && python3 -m pytest tests/memory/test_backend_integration.py -v`
Expected: 3 passed

- [ ] **Step 3: Commit**

```bash
cd /home/xiowen/code/merco
git add tests/memory/test_backend_integration.py
git commit -m "test: MemoryBackend backward compatibility integration"
```

---

## Task 6: 文档更新

**Files:**
- Modify: `docs/project-vision/references/progress.md`

- [ ] **Step 1: Update progress.md**

Add a new section for MemoryBackend pluginization.

- [ ] **Step 2: Commit**

```bash
cd /home/xiowen/code/merco
git add docs/project-vision/references/progress.md
git commit -m "docs: update progress.md for MemoryBackend pluginization"
```

---

## Self-Review

**Spec coverage:**
- ✅ MemoryBackend ABC (Task 1)
- ✅ MemoryBackendRegistry (Task 1)
- ✅ JSONBackend (Task 2)
- ✅ MemoryStore facade (Task 3)
- ✅ PluginContext memory_backends (Task 4)
- ✅ Config memory.backend 字段 (Task 4)
- ✅ Agent 装配 + selected_backend (Task 4)
- ✅ 向后兼容 (Task 5)
- ✅ 文档 (Task 6)

**Placeholder scan:** 无

**Type consistency:** MemoryBackend 接口与 MemoryStore facade 方法签名一致
