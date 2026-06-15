# 集成测试补全 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 补充 mock LLM 的 Agent-Loop 集成测试，覆盖 6 个缺失场景（context 压缩、memory recall 注入、memory save、recovery retry、hook events、mcp tool E2E）

**Architecture:** 全部用 `MockLLMClient` + `test_agent` fixture + `tmp_path` session store；测试分散到现有 4 个文件，按场景就近落位

**Tech Stack:** pytest, pytest-asyncio, MockLLMClient (conftest.py), SessionStore (SQLite), MemoryStore (JSON)

---

## 文件结构

| 文件 | 变更类型 | 职责 |
|------|---------|------|
| `tests/integration/test_scenarios.py` | 修改 | +5 tests: 压缩/fork/recovery/recall_e2e/mcp_e2e |
| `tests/integration/test_memory_lifecycle.py` | 修改 | +2 tests: memory recall 注入端到端 + memory save 事件 |
| `tests/memory/test_recall.py` | 修改 | +3 tests: HybridRecaller/FTS5Recaller/MemoryRecaller 直接验证（已有基础，扩展） |
| `tests/observability/test_observer.py` | 修改 | +1 test: hook 事件计数（during run loop） |
| `docs/project-vision/references/progress.md` | 修改 | 更新 next steps |

---

## Task 1: Context 压缩集成测试

**Files:**
- Modify: `tests/integration/test_scenarios.py` (append 1 test)
- Read: `merco/core/compressor.py`, `merco/core/agent.py:_compress_context`

- [ ] **Step 1: Append test to test_scenarios.py**

```python
@pytest.mark.asyncio
async def test_context_compression_triggered(test_agent):
    """MockLLM 产生 N 条大消息 → context 超过阈值 → 压缩 → messages 变少"""
    # 构造大上下文：每条 ~5000 chars，触发 75% 阈值
    big_msg = "x" * 5000
    test_agent.config.max_input_tokens = 20000  # 阈值 15000 tokens

    # Mock LLM 第一次返回普通消息，第二次返回压缩后续消息
    test_agent.llm = MockLLMClient([
        {"content": big_msg},  # 第 1 轮
        {"content": big_msg},  # 第 2 轮
        {"content": big_msg},  # 第 3 轮
        {"content": big_msg},  # 第 4 轮 — 累积到 > 15000 tokens，触发压缩
        {"content": "压缩后继续"},  # 压缩后第 5 轮
    ])

    # 跑 4 轮
    for i in range(4):
        await test_agent.run(f"msg {i}")

    # 验证：context.messages 已被压缩（小于 4 轮的 8 条）
    assert len(test_agent.context.messages) < 8

    # 验证：session 持久化了所有消息
    test_agent.session.save()
    all_msgs = test_agent._session_store.load_messages(test_agent.session.id)
    assert len(all_msgs) == 8  # session 完整保存（压缩只在 context 层）
```

- [ ] **Step 2: Run test to verify it passes**

Run: `cd /home/xiowen/code/merco && python3 -m pytest tests/integration/test_scenarios.py::test_context_compression_triggered -v`
Expected: PASS (现有代码已支持)

- [ ] **Step 3: Commit**

```bash
cd /home/xiowen/code/merco
git add tests/integration/test_scenarios.py
git commit -m "test: integration test for context compression"
```

---

## Task 2: Session fork on compress 集成测试

**Files:**
- Modify: `tests/integration/test_scenarios.py` (append 1 test)

- [ ] **Step 1: Append test**

```python
@pytest.mark.asyncio
async def test_session_fork_on_compress(test_agent):
    """压缩时自动 fork 当前 session 到 child"""
    test_agent.config.fork_enabled = True
    test_agent.config.fork_auto_on_compress = True
    test_agent.config.max_input_tokens = 20000

    big_msg = "x" * 5000
    test_agent.llm = MockLLMClient([
        {"content": big_msg},
        {"content": big_msg},
        {"content": big_msg},
        {"content": big_msg},
        {"content": big_msg},  # 触发压缩 → fork
    ])

    original_session_id = test_agent.session.id

    # 跑 5 轮触发压缩
    for i in range(5):
        await test_agent.run(f"msg {i}")

    # 验证：session store 至少 2 个 session（原 + fork）
    sessions = test_agent._session_store.list_sessions()
    assert len(sessions) >= 2

    # 验证：fork session 包含原始消息
    children = test_agent._session_store.get_children(original_session_id)
    assert len(children) >= 1
    forked = children[0]
    forked_msgs = test_agent._session_store.load_messages(forked["id"])
    assert len(forked_msgs) > 0
```

- [ ] **Step 2: Run test to verify it passes**

Run: `cd /home/xiowen/code/merco && python3 -m pytest tests/integration/test_scenarios.py::test_session_fork_on_compress -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
cd /home/xiowen/code/merco
git add tests/integration/test_scenarios.py
git commit -m "test: integration test for session fork on compress"
```

---

## Task 3: Memory recall 直接测试（HybridRecaller 聚合）

**Files:**
- Modify: `tests/memory/test_recall.py` (append 1 test in `class TestHybridRecaller`)

- [ ] **Step 1: Append test in TestHybridRecaller**

```python
async def test_hybrid_with_real_store_and_search(tmp_path):
    """HybridRecaller 聚合 FTS5Recaller + MemoryRecaller，从真实数据召回"""
    from merco.memory.store import MemoryStore
    from merco.memory.session_store import SessionStore
    from merco.memory.session_search import SessionSearch

    # 真实 store
    session_store = SessionStore(str(tmp_path / "sess.db"))
    mem_store = MemoryStore(str(tmp_path / "memory"))

    # 写入 session message
    session_store.save_message("s1", "user", "Python programming")
    session_store.save_message("s1", "assistant", "I can help with Python")
    session_store.save_message("s1", "user", "Java is also good")

    # 写入 memory
    mem_store.save("user_lang", "Python", tags=["[user]"])

    # 构造 HybridRecaller
    fts5 = FTS5Recaller(SessionSearch(session_store))
    mem = MemoryRecaller(mem_store)
    hybrid = HybridRecaller(limit=5, max_chars=500).add(fts5).add(mem)

    # 召回
    results = await hybrid.recall("Python")
    assert len(results) >= 1

    # 验证 source 字段标识
    sources = {r.source for r in results}
    assert "fts5" in sources or "memory" in sources
```

- [ ] **Step 2: Run test to verify it passes**

Run: `cd /home/xiowen/code/merco && python3 -m pytest tests/memory/test_recall.py::test_hybrid_with_real_store_and_search -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
cd /home/xiowen/code/merco
git add tests/memory/test_recall.py
git commit -m "test: HybridRecaller with real data integration"
```

---

## Task 4: Memory recall 注入 system prompt 端到端

**Files:**
- Modify: `tests/integration/test_memory_lifecycle.py` (append 1 test)

- [ ] **Step 1: Append test**

```python
async def test_recall_injects_into_system_prompt(test_agent):
    """存记忆 → agent.run() → system prompt 含记忆内容"""
    # 存记忆
    test_agent._memory_store.save("user_name", "小王", tags=["[user]"])

    # 构造会让系统调用 recaller 的 user prompt
    test_agent.llm = MockLLMClient([{"content": "你好小王"}])

    # 跑一轮
    await test_agent.run("你知道我叫什么吗？")

    # 验证：system prompt 包含记忆
    sys_msg = test_agent.context.messages[0]
    assert sys_msg["role"] == "system"
    # system content 可能在 chunk 里或拼接
    sys_content = sys_msg.get("content", "")
    # _build_system_prompt 拼接的 system prompt 可能在多个 chunk 里
    all_sys = sys_content
    for m in test_agent.context.messages[1:]:
        if m.get("role") == "system":
            all_sys += m.get("content", "")
    assert "小王" in all_sys or "user_name" in all_sys
```

- [ ] **Step 2: Run test to verify it passes**

Run: `cd /home/xiowen/code/merco && python3 -m pytest tests/integration/test_memory_lifecycle.py::test_recall_injects_into_system_prompt -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
cd /home/xiowen/code/merco
git add tests/integration/test_memory_lifecycle.py
git commit -m "test: memory recall injects into system prompt E2E"
```

---

## Task 5: Memory save 全链路 + memory.saved 事件

**Files:**
- Modify: `tests/integration/test_memory_lifecycle.py` (append 1 test)

- [ ] **Step 1: Append test**

```python
async def test_memory_save_emits_event(test_agent):
    """/remember → Strategy → Pipeline → Store + memory.saved 事件"""
    # 注册事件 handler
    saved_events = []

    async def on_saved(key, **kwargs):
        saved_events.append(key)

    test_agent.hooks.on("memory.saved", on_saved)

    # 触发 command.remember
    await test_agent.hooks.emit(
        "command.remember", text="我喜欢用中文", key="user_lang_pref"
    )

    # 验证：store 写入成功
    record = test_agent._memory_store.load("user_lang_pref")
    assert record is not None
    assert record["value"] == "我喜欢用中文"
    assert "[user]" in record["tags"]

    # 验证：memory.saved 事件触发
    assert "user_lang_pref" in saved_events
```

- [ ] **Step 2: Run test to verify it passes**

Run: `cd /home/xiowen/code/merco && python3 -m pytest tests/integration/test_memory_lifecycle.py::test_memory_save_emits_event -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
cd /home/xiowen/code/merco
git add tests/integration/test_memory_lifecycle.py
git commit -m "test: memory save pipeline emits memory.saved event"
```

---

## Task 6: RecoveryPipeline 重试集成测试

**Files:**
- Modify: `tests/integration/test_scenarios.py` (append 1 test)

- [ ] **Step 1: Append test**

```python
@pytest.mark.asyncio
async def test_recovery_pipeline_retries_on_5xx(test_agent):
    """MockLLM 第一次抛 500 → RecoveryPipeline 重试 → 第二次成功"""
    from openai import APIStatusError

    class FlakyLLM:
        def __init__(self):
            self.calls = 0

        async def chat(self, messages, tools=None, tool_choice="auto"):
            self.calls += 1
            if self.calls == 1:
                # 第一次抛 500 错误
                raise APIStatusError(
                    "internal server error",
                    request=MagicMock(),
                    body={"error": "server error"},
                    code=500,
                )
            # 第二次返回成功
            return {"content": "重试后成功", "finish_reason": "stop"}

        async def chat_stream(self, messages, tools=None, tool_choice="auto"):
            resp = await self.chat(messages, tools, tool_choice)
            yield resp

    test_agent.llm = FlakyLLM()
    test_agent.config.max_tool_calls = 10

    # 跑一轮：第一次失败 → 重试 → 第二次成功
    result = await test_agent.run("hello")
    assert result == "重试后成功"
    # LLM 至少被调用 2 次（第一次失败 + 重试成功）
    assert test_agent.llm.calls >= 2
```

- [ ] **Step 2: Run test to verify it passes**

Run: `cd /home/xiowen/code/merco && python3 -m pytest tests/integration/test_scenarios.py::test_recovery_pipeline_retries_on_5xx -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
cd /home/xiowen/code/merco
git add tests/integration/test_scenarios.py
git commit -m "test: RecoveryPipeline retries on 5xx"
```

---

## Task 7: Hook 事件计数 during loop

**Files:**
- Modify: `tests/observability/test_observer.py` (append 1 test)

- [ ] **Step 1: Append test**

```python
def test_observer_counts_hook_events_in_agent_loop(test_agent, monkeypatch):
    """agent.run() 触发后，Observer 内部计数应正确更新"""
    from rich.console import Console
    from io import StringIO
    from merco.observability.observer import Observer

    # 替换 console 避免噪声
    quiet = Console(file=StringIO(), force_terminal=True, width=120)
    monkeypatch.setattr("merco.core.agent.console", quiet)

    # Observer 注入（先 off 再 on 现有 hook）
    observer = Observer(test_agent.hooks)
    test_agent.llm = MockLLMClient([
        {"tool_calls": [{"id": "t1", "name": "echo", "arguments": {"message": "hi"}}]},
        {"content": "done"},
    ])

    # 跑一轮带工具调用
    import asyncio
    asyncio.get_event_loop().run_until_complete(test_agent.run("echo hi"))

    # 验证 Observer 计数
    counters = observer._live.get_counters()
    assert counters.get("llm_calls", 0) >= 1  # 至少 1 次 LLM 调用
    # tool_calls 至少 1 次（tool.after_execute 事件）
    assert counters.get("tool_calls", 0) >= 1 or counters.get("tool_executions", 0) >= 1
    # conversation.turn 至少 1 次
    assert counters.get("turns", 0) >= 1 or counters.get("conversation_turns", 0) >= 1
```

**注**: 如果 Observer 计数器 key 名不同（如 `tool_errors` / `llm_tokens_in` 等），根据 `merco/observability/observer.py:_on_tool` / `_on_llm` 实际 increment 的 key 名调整。可通过 `grep -n "self._live.increment" merco/observability/observer.py` 确认。

- [ ] **Step 2: Run test, iterate on counter names until pass**

Run: `cd /home/xiowen/code/merco && python3 -m pytest tests/observability/test_observer.py::test_observer_counts_hook_events_in_agent_loop -v`
Expected: PASS（可能需要先 `grep "self._live.increment" merco/observability/observer.py` 确认 counter key 名）

- [ ] **Step 3: Commit**

```bash
cd /home/xiowen/code/merco
git add tests/observability/test_observer.py
git commit -m "test: observer counts hook events during agent loop"
```

---

## Task 8: MCP tool calling E2E

**Files:**
- Modify: `tests/integration/test_scenarios.py` (append 1 test)
- Read: `tests/mcp/test_manager.py` for mock MCP server pattern

- [ ] **Step 1: Read existing MCP test patterns**

Run: `cd /home/xiowen/code/merco && head -80 tests/mcp/test_manager.py`

- [ ] **Step 2: Append test**

```python
@pytest.mark.asyncio
async def test_mcp_tool_calling_e2e(test_agent, tmp_path):
    """MCP tool 通过 agent.run() 端到端调用 → result 正确"""
    # 注册一个 mock MCP tool
    from merco.tools.base import BaseTool
    from merco.tools.registry import ToolRegistry

    class MockMCPTool(BaseTool):
        name = "mcp_test_tool"
        description = "MCP test tool"
        toolset = "mcp"
        parameters = {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        }

        async def execute(self, query: str, **kwargs):
            return {"result": f"mcp: {query}"}

    # 把 MCP tool 加入 registry
    test_agent.tool_registry.register(MockMCPTool())

    # Mock LLM：第一次 tool_call → 第二次答
    test_agent.llm = MockLLMClient([
        {
            "tool_calls": [{
                "id": "mcp_t1",
                "name": "mcp_test_tool",
                "arguments": {"query": "test query"},
            }],
        },
        {"content": "MCP 工具返回了结果"},
    ])

    result = await test_agent.run("用 mcp 工具查 test query")
    assert "MCP 工具返回了结果" in result

    # 验证：tool result 注入 session
    msgs = test_agent.session.messages
    assert any(m["role"] == "tool" and "mcp: test query" in str(m.get("content", "")) for m in msgs)
```

- [ ] **Step 3: Run test to verify it passes**

Run: `cd /home/xiowen/code/merco && python3 -m pytest tests/integration/test_scenarios.py::test_mcp_tool_calling_e2e -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
cd /home/xiowen/code/merco
git add tests/integration/test_scenarios.py
git commit -m "test: MCP tool calling E2E"
```

---

## Task 9: 全部集成测试运行 + 文档更新

**Files:**
- Modify: `docs/project-vision/references/progress.md` (update "下一步" + current status)

- [ ] **Step 1: Run all new tests**

Run: `cd /home/xiowen/code/merco && python3 -m pytest tests/integration/test_scenarios.py tests/integration/test_memory_lifecycle.py tests/memory/test_recall.py tests/observability/test_observer.py -v 2>&1 | tail -20`

Expected: 8 new tests pass + existing tests still pass

- [ ] **Step 2: Update progress.md**

Modify the "本次会话更新 (2026-06-15)" section to add 2026-06-16 entry:

```markdown
### 本次会话更新 (2026-06-16)

- **集成测试补全（新功能）**: +8 个集成测试覆盖 6 个场景：
  - Context 压缩 + Session fork on compress
  - Memory recall 注入 system prompt 端到端 + HybridRecaller 真实数据
  - Memory save 全链路 + `memory.saved` 事件
  - RecoveryPipeline 重试（500 错误 → 第二次成功）
  - Hook 事件计数 during loop
  - MCP tool calling 端到端
  - 全部用 MockLLMClient + test_agent fixture，零网络依赖
```

- [ ] **Step 3: Commit**

```bash
cd /home/xiowen/code/merco
git add docs/project-vision/references/progress.md
git commit -m "docs: progress.md update for integration test coverage"
```

---

## Self-Review

**Spec coverage:**
- ✅ 场景 1: Context 压缩 + fork (Tasks 1, 2)
- ✅ 场景 2: Memory recall 注入 (Tasks 3, 4)
- ✅ 场景 3: Memory save 全链路 (Task 5)
- ✅ 场景 4: RecoveryPipeline 重试 (Task 6)
- ✅ 场景 5: Hook 事件 (Task 7)
- ✅ 场景 6: MCP tool E2E (Task 8)

**Placeholder scan:** 无 "TBD" / "TODO" / "implement later"。

**Type consistency:** 
- `test_agent` fixture 在 conftest.py 定义
- `MockLLMClient` 在 conftest.py 定义
- `test_agent._memory_store`、`test_agent.hooks`、`test_agent.context`、`test_agent.session` 在 agent.py 已暴露
- `test_agent._session_store` 暴露（agent.py:374）
- `test_agent.tool_registry` 暴露

**已知可能问题:**
- Task 7 (Observer counter names): 需根据实际 `observer.py` 调整 — 已在 Step 2 注明用 grep 确认
- Task 6 (RecoveryPipeline): APIStatusError 导入路径可能因 openai 版本不同 — Step 1 注明
