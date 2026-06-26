# merco Context Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建 Context Pipeline 系统，让上下文处理（压缩、缓存优化）成为可扩展的处理器链

**Architecture:** ContextProcessor ABC + ContextPipeline 处理链 + CompressProcessor（迁移现有逻辑）+ CacheOptimizeProcessor（新增）+ PluginContext 扩展 + Agent 集成

**Tech Stack:** Python 3.12, ABC, asyncio

---

## 文件结构

| 文件 | 职责 |
|------|------|
| `merco/context/__init__.py` | 导出 ContextProcessor, ContextPipeline |
| `merco/context/pipeline.py` | ContextProcessor ABC + ContextPipeline |
| `merco/context/processors/__init__.py` | 处理器包 |
| `merco/context/processors/compress.py` | CompressProcessor（迁移自 ContextCompressor） |
| `merco/context/processors/cache_optimize.py` | CacheOptimizeProcessor |
| `merco/plugins/base.py` | PluginContext 新增 context_pipeline |
| `merco/core/agent.py` | 装配 ContextPipeline，替换 _compress_context |
| `tests/context/test_pipeline.py` | Pipeline 单测 |
| `tests/context/test_processors.py` | 处理器单测 |
| `tests/integration/test_context_pipeline.py` | 端到端集成测试 |

---

## Task 1: ContextProcessor + ContextPipeline

**Files:**
- Create: `merco/context/__init__.py`
- Create: `merco/context/pipeline.py`
- Test: `tests/context/test_pipeline.py`

- [ ] **Step 1: Write the failing test**

Create `tests/context/__init__.py` (empty) and `tests/context/test_pipeline.py`:

```python
"""ContextPipeline 单测"""
import pytest
from merco.context.pipeline import ContextProcessor, ContextPipeline


class AppendProcessor(ContextProcessor):
    """测试用处理器：追加一条消息"""
    name = "append"

    def __init__(self, content: str):
        self.content = content

    async def process(self, messages, **kwargs):
        return messages + [{"role": "system", "content": self.content}]


class DoubleProcessor(ContextProcessor):
    """测试用处理器：复制所有消息"""
    name = "double"

    async def process(self, messages, **kwargs):
        return messages + messages


@pytest.fixture
def pipeline():
    return ContextPipeline()


async def test_pipeline_empty(pipeline):
    """空管线返回原消息"""
    msgs = [{"role": "user", "content": "hi"}]
    result = await pipeline.run(msgs)
    assert result == msgs


async def test_pipeline_single_processor(pipeline):
    """单处理器"""
    pipeline.use(AppendProcessor("added"))
    msgs = [{"role": "user", "content": "hi"}]
    result = await pipeline.run(msgs)
    assert len(result) == 2
    assert result[1]["content"] == "added"


async def test_pipeline_order(pipeline):
    """处理器按注册顺序执行"""
    pipeline.use(AppendProcessor("first"))
    pipeline.use(AppendProcessor("second"))
    msgs = [{"role": "user", "content": "hi"}]
    result = await pipeline.run(msgs)
    assert len(result) == 3
    assert result[1]["content"] == "first"
    assert result[2]["content"] == "second"


async def test_pipeline_chaining(pipeline):
    """处理器链式执行：第一个的输出是第二个的输入"""
    pipeline.use(AppendProcessor("added"))
    pipeline.use(DoubleProcessor())
    msgs = [{"role": "user", "content": "hi"}]
    result = await pipeline.run(msgs)
    assert len(result) == 4  # 2 from first + 2 from double
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/xiowen/code/merco && python3 -m pytest tests/context/test_pipeline.py -v`
Expected: ImportError (merco.context.pipeline not exists)

- [ ] **Step 3: Implement ContextProcessor + ContextPipeline**

Create `merco/context/__init__.py`:

```python
"""上下文处理管线"""

from .pipeline import ContextProcessor, ContextPipeline

__all__ = ["ContextProcessor", "ContextPipeline"]
```

Create `merco/context/pipeline.py`:

```python
"""ContextProcessor ABC + ContextPipeline"""
from __future__ import annotations

from abc import ABC, abstractmethod


class ContextProcessor(ABC):
    """上下文处理器基类"""
    name: str = ""

    @abstractmethod
    async def process(self, messages: list[dict], **kwargs) -> list[dict]:
        """处理消息列表，返回处理后的消息列表"""
        ...


class ContextPipeline:
    """上下文处理管线 — 按注册顺序执行处理器"""

    def __init__(self):
        self._processors: list[ContextProcessor] = []

    def use(self, processor: ContextProcessor) -> ContextPipeline:
        """注册处理器"""
        self._processors.append(processor)
        return self

    async def run(self, messages: list[dict], **kwargs) -> list[dict]:
        """按顺序执行所有处理器"""
        for p in self._processors:
            messages = await p.process(messages, **kwargs)
        return messages
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/xiowen/code/merco && python3 -m pytest tests/context/test_pipeline.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
cd /home/xiowen/code/merco
git add merco/context/ tests/context/
git commit -m "feat: add ContextProcessor and ContextPipeline"
```

---

## Task 2: CompressProcessor（迁移自 ContextCompressor）

**Files:**
- Create: `merco/context/processors/__init__.py`
- Create: `merco/context/processors/compress.py`
- Test: `tests/context/test_processors.py`

- [ ] **Step 1: Write the failing test**

Create `tests/context/test_processors.py`:

```python
"""处理器单测"""
import pytest
from merco.context.processors.compress import CompressProcessor
from merco.context.processors.cache_optimize import CacheOptimizeProcessor


class TestCompressProcessor:
    async def test_below_threshold_no_compress(self):
        """低于阈值不压缩"""
        proc = CompressProcessor(max_tokens=10000, threshold=0.75)
        msgs = [{"role": "user", "content": "hi"}]
        result = await proc.process(msgs)
        assert result == msgs

    async def test_above_threshold_compress(self):
        """超过阈值触发压缩"""
        proc = CompressProcessor(max_tokens=100, threshold=0.5)
        # 构造大消息超过阈值
        big_msg = {"role": "user", "content": "x" * 500}
        msgs = [
            {"role": "user", "content": "old1"},
            {"role": "assistant", "content": "reply1"},
            {"role": "user", "content": "old2"},
            {"role": "assistant", "content": "reply2"},
            {"role": "user", "content": "old3"},
            {"role": "assistant", "content": "reply3"},
            big_msg,
        ]
        result = await proc.process(msgs)
        assert len(result) < len(msgs)

    async def test_truncate_strategy(self):
        """truncate 策略截断消息"""
        proc = CompressProcessor(max_tokens=100, threshold=0.5)
        msgs = [{"role": "user", "content": f"msg{i}"} for i in range(10)]
        result = await proc.process(msgs, compress_strategy="truncate")
        assert len(result) <= len(msgs)


class TestCacheOptimizeProcessor:
    async def test_system_messages_first(self):
        """system 消息排在前面"""
        proc = CacheOptimizeProcessor()
        msgs = [
            {"role": "user", "content": "hi"},
            {"role": "system", "content": "system prompt"},
            {"role": "assistant", "content": "hello"},
        ]
        result = await proc.process(msgs)
        assert result[0]["role"] == "system"

    async def test_summary_messages_stable(self):
        """摘要消息视为稳定"""
        proc = CacheOptimizeProcessor()
        msgs = [
            {"role": "user", "content": "hi"},
            {"role": "system", "content": "[Earlier conversation summary] ..."},
        ]
        result = await proc.process(msgs)
        assert "[Earlier conversation summary]" in result[0]["content"]

    async def test_memory_messages_stable(self):
        """记忆消息视为稳定"""
        proc = CacheOptimizeProcessor()
        msgs = [
            {"role": "user", "content": "hi"},
            {"role": "system", "content": "[memory] user preference"},
        ]
        result = await proc.process(msgs)
        assert "[memory]" in result[0]["content"]

    async def test_empty_messages(self):
        """空消息列表"""
        proc = CacheOptimizeProcessor()
        result = await proc.process([])
        assert result == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/xiowen/code/merco && python3 -m pytest tests/context/test_processors.py -v`
Expected: ImportError

- [ ] **Step 3: Implement CompressProcessor**

Create `merco/context/processors/__init__.py`:

```python
"""上下文处理器"""
```

Create `merco/context/processors/compress.py`:

```python
"""CompressProcessor — 替代 ContextCompressor"""
from __future__ import annotations

import logging
from merco.context.pipeline import ContextProcessor
from merco.core.context import msg_tokens

logger = logging.getLogger("merco.context.compress")


class CompressProcessor(ContextProcessor):
    """压缩：超过阈值时摘要旧消息"""
    name = "compress"

    def __init__(self, max_tokens: int = 64000, threshold: float = 0.75):
        self.max_tokens = max_tokens
        self.threshold = threshold

    async def process(self, messages: list[dict], **kwargs) -> list[dict]:
        total = sum(msg_tokens(m) for m in messages)
        trigger = int(self.max_tokens * self.threshold)
        if total <= trigger or len(messages) <= 4:
            return messages

        strategy = kwargs.get("compress_strategy", "sliding")
        summary_fn = kwargs.get("summary_fn")

        if strategy == "sliding":
            return await self._sliding(messages, summary_fn)
        elif strategy == "truncate":
            return self._truncate(messages)
        return messages

    async def _sliding(self, messages: list[dict], summary_fn=None) -> list[dict]:
        """滑动窗口压缩 — 保留最后 2 轮原文 + 摘要旧消息"""
        TAIL_TURNS = 2

        tail_start = 0
        user_count = 0
        for i in range(len(messages) - 1, -1, -1):
            if messages[i].get("role") == "user":
                user_count += 1
                if user_count >= TAIL_TURNS:
                    tail_start = i
                    break

        body = messages[:tail_start]
        tail = messages[tail_start:]

        if not body:
            return messages

        if summary_fn:
            try:
                summary_text = await summary_fn(body)
                summary = {"role": "system", "content": summary_text}
            except Exception as e:
                logger.warning("LLM 摘要失败: %s, fallback", e)
                summary = self._build_summary(body)
        else:
            summary = self._build_summary(body)

        result = [m for m in tail if m.get("role") == "system"][:1]
        result.append(summary)
        result.extend(m for m in tail if m.get("role") != "system")

        before = sum(msg_tokens(m) for m in messages)
        after = sum(msg_tokens(m) for m in result)
        logger.debug("压缩: %d条(%dtok) → %d条(%dtok)", len(messages), before, len(result), after)
        return result

    def _truncate(self, messages: list[dict]) -> list[dict]:
        """简单截断 fallback"""
        if len(messages) <= 6:
            return messages
        kept = messages[-6:]
        return self._extend_to_chain(messages, messages[:-6], kept)

    def _extend_to_chain(self, all_messages, before, kept):
        """补全孤立 tool 消息的前导 assistant"""
        while True:
            orphan_at = None
            for i, msg in enumerate(kept):
                if msg.get("role") != "tool":
                    continue
                prev = kept[i - 1] if i > 0 else None
                if not (prev and prev.get("role") == "assistant" and prev.get("tool_calls")):
                    orphan_at = i
                    break
            if orphan_at is None:
                break
            try:
                orig_idx = all_messages.index(kept[orphan_at])
            except ValueError:
                break
            found = None
            for j in range(orig_idx - 1, -1, -1):
                msg = all_messages[j]
                if msg.get("role") == "assistant" and msg.get("tool_calls"):
                    found = msg
                    break
            if found is None or found in kept:
                break
            kept.insert(0, found)
        return kept

    def _build_summary(self, messages: list[dict]) -> dict:
        """Fallback 摘要"""
        user_msgs = [m for m in messages if m.get("role") == "user"]
        preview = []
        for um in user_msgs[-5:]:
            c = um.get("content", "")[:60]
            if c:
                preview.append(f"• {c}")
        intro = (
            f"[压缩了 {len(messages)} 条历史消息。"
            f"最近讨论: {'; '.join(preview) if preview else '无'}。"
            f"详细历史请用 /search 查询。]"
        )
        return {"role": "system", "content": intro}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/xiowen/code/merco && python3 -m pytest tests/context/test_processors.py -v`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
cd /home/xiowen/code/merco
git add merco/context/processors/ tests/context/test_processors.py
git commit -m "feat: add CompressProcessor (migrated from ContextCompressor)"
```

---

## Task 3: CacheOptimizeProcessor

**Files:**
- Create: `merco/context/processors/cache_optimize.py`
- Test: `tests/context/test_processors.py` (append)

- [ ] **Step 1: Append test to test_processors.py**

The tests for CacheOptimizeProcessor are already in the test file from Task 2.

- [ ] **Step 2: Implement CacheOptimizeProcessor**

Create `merco/context/processors/cache_optimize.py`:

```python
"""CacheOptimizeProcessor — 提高 LLM 缓存命中率"""
from __future__ import annotations

from merco.context.pipeline import ContextProcessor


class CacheOptimizeProcessor(ContextProcessor):
    """缓存优化：重排序让稳定内容在前"""
    name = "cache_optimize"

    async def process(self, messages: list[dict], **kwargs) -> list[dict]:
        stable = []
        volatile = []

        for msg in messages:
            if self._is_stable(msg):
                stable.append(msg)
            else:
                volatile.append(msg)

        return stable + volatile

    def _is_stable(self, msg: dict) -> bool:
        """判断消息是否稳定（可缓存）"""
        role = msg.get("role", "")
        if role == "system":
            return True
        content = str(msg.get("content", ""))
        if "[Earlier conversation summary]" in content:
            return True
        if "[memory]" in content:
            return True
        return False
```

- [ ] **Step 3: Run test to verify it passes**

Run: `cd /home/xiowen/code/merco && python3 -m pytest tests/context/test_processors.py -v`
Expected: 7 passed

- [ ] **Step 4: Commit**

```bash
cd /home/xiowen/code/merco
git add merco/context/processors/cache_optimize.py
git commit -m "feat: add CacheOptimizeProcessor"
```

---

## Task 4: PluginContext 扩展

**Files:**
- Modify: `merco/plugins/base.py`

- [ ] **Step 1: Add context_pipeline to PluginContext**

Add one new optional parameter to PluginContext.__init__:

```python
    context_pipeline: "ContextPipeline" = None,
```

Store as `self.context_pipeline = context_pipeline`.

- [ ] **Step 2: Verify syntax**

Run: `cd /home/xiowen/code/merco && python3 -m py_compile merco/plugins/base.py && echo "Syntax OK"`

- [ ] **Step 3: Run existing plugin tests**

Run: `cd /home/xiowen/code/merco && python3 -m pytest tests/plugins/ -v`
Expected: all pass

- [ ] **Step 4: Commit**

```bash
cd /home/xiowen/code/merco
git add merco/plugins/base.py
git commit -m "feat: extend PluginContext with context_pipeline"
```

---

## Task 5: Agent 集成

**Files:**
- Modify: `merco/core/agent.py`

- [ ] **Step 1: Add ContextPipeline to Agent.__init__**

After the PluginContext creation block, add:

```python
        # ── Context Pipeline ──
        from merco.context.pipeline import ContextPipeline
        from merco.context.processors.compress import CompressProcessor
        from merco.context.processors.cache_optimize import CacheOptimizeProcessor

        self.context_pipeline = ContextPipeline()
        self.context_pipeline.use(CacheOptimizeProcessor())
        self.context_pipeline.use(CompressProcessor(
            max_tokens=config.max_input_tokens,
            threshold=config.compression_threshold,
        ))
        self._plugin_ctx.context_pipeline = self.context_pipeline
```

- [ ] **Step 2: Replace _compress_context**

Find `Agent._compress_context` and replace the compressor logic with pipeline call:

```python
    async def _compress_context(self):
        """压缩上下文"""
        # ... existing backup/fork logic stays ...

        # 替换 ContextCompressor 为 ContextPipeline
        messages = await self.context_pipeline.run(
            self.context.messages,
            summary_fn=self._llm_summary if hasattr(self, '_llm_summary') else None,
            compress_strategy="sliding",
        )
        self.context.messages = messages

        # ... existing post-compression logic stays ...
```

- [ ] **Step 3: Verify syntax**

Run: `cd /home/xiowen/code/merco && python3 -m py_compile merco/core/agent.py && echo "Syntax OK"`

- [ ] **Step 4: Run existing integration tests**

Run: `cd /home/xiowen/code/merco && python3 -m pytest tests/integration/test_scenarios.py -v -k "test_simple_conversation" 2>&1 | tail -10`
Expected: pass

- [ ] **Step 5: Commit**

```bash
cd /home/xiowen/code/merco
git add merco/core/agent.py
git commit -m "feat: wire ContextPipeline into Agent, replace ContextCompressor"
```

---

## Task 6: 端到端集成测试

**Files:**
- Create: `tests/integration/test_context_pipeline.py`

- [ ] **Step 1: Write integration test**

Create `tests/integration/test_context_pipeline.py`:

```python
"""Context Pipeline 端到端集成测试"""
import pytest
from merco.context.pipeline import ContextPipeline
from merco.context.processors.compress import CompressProcessor
from merco.context.processors.cache_optimize import CacheOptimizeProcessor


async def test_pipeline_with_compress(test_agent):
    """Context Pipeline 压缩端到端"""
    # 构造大上下文触发压缩
    test_agent.config.max_input_tokens = 20000
    test_agent.context.max_tokens = 20000

    big_msg = "x" * 22000
    test_agent.llm = type('MockLLM', (), {
        'calls': [],
        'chat': lambda self, messages, **kw: {"content": "compressed"},
        'chat_stream': lambda self, messages, **kw: iter([{"content": "compressed"}]),
    })()

    # 跑 4 轮触发压缩
    for i in range(4):
        await test_agent.run(f"msg {i}")

    # 验证 context 被压缩
    assert len(test_agent.context.messages) < 8


async def test_cache_optimize_processor():
    """CacheOptimizeProcessor 重排序"""
    proc = CacheOptimizeProcessor()
    msgs = [
        {"role": "user", "content": "hi"},
        {"role": "system", "content": "system prompt"},
        {"role": "assistant", "content": "hello"},
    ]
    result = await proc.process(msgs)
    assert result[0]["role"] == "system"
    assert result[1]["role"] == "user"
    assert result[2]["role"] == "assistant"
```

- [ ] **Step 2: Run test**

Run: `cd /home/xiowen/code/merco && python3 -m pytest tests/integration/test_context_pipeline.py -v`
Expected: 2 passed

- [ ] **Step 3: Commit**

```bash
cd /home/xiowen/code/merco
git add tests/integration/test_context_pipeline.py
git commit -m "test: Context Pipeline end-to-end integration"
```

---

## Task 7: 文档更新

**Files:**
- Modify: `docs/project-vision/references/progress.md`

- [ ] **Step 1: Update progress.md**

Add a new section for the Context Pipeline system in the "本次会话更新" area.

- [ ] **Step 2: Commit**

```bash
cd /home/xiowen/code/merco
git add docs/project-vision/references/progress.md
git commit -m "docs: update progress.md for Context Pipeline"
```

---

## Self-Review

**Spec coverage:**
- ✅ ContextProcessor ABC (Task 1)
- ✅ ContextPipeline (Task 1)
- ✅ CompressProcessor (Task 2)
- ✅ CacheOptimizeProcessor (Task 3)
- ✅ PluginContext 扩展 (Task 4)
- ✅ Agent 集成 (Task 5)
- ✅ 端到端集成测试 (Task 6)
- ✅ 文档更新 (Task 7)

**Placeholder scan:** 无 TBD/TODO

**Type consistency:** ContextProcessor.process 签名、ContextPipeline.run 签名在所有 task 中一致
