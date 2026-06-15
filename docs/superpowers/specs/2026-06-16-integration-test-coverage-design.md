# 集成测试补全设计

> 最后更新: 2026-06-16

## 目标

补充 mock LLM 的 Agent-Loop 集成测试，覆盖现有功能中缺失的 6 个关键场景：Context 压缩 + fork、Memory recall 注入、Memory save 全链路、RecoveryPipeline 重试、Hook 事件计数、MCP tool calling E2E。

## 现状

- 266 个测试，基础场景已覆盖（对话 + 工具调用、Session 持久化、流式 reasoning/content）
- `test_agent` fixture（MockLLMClient + test tools + tmp session store）和 `StreamingMockLLMClient` 已成熟
- 6 个关键场景**未覆盖**

## 目标场景

### 场景 1: Context 压缩 + fork on compress

**测试文件**: `tests/integration/test_scenarios.py`
**策略**: MockLLMClient 产生 N 条消息触发 `context.needs_compression()` → 验证 messages 被压缩 + `session.fork()` 被调用（session store 中出现新 child session）

**验证点**:
- 压缩后 `context.messages` 长度 < 压缩前
- 压缩后 `context.messages` 包含 summary 消息
- `session.store.clone_session()` 被调用，child session 存在

### 场景 2: Memory recall 注入 system prompt

**测试文件**: `tests/memory/test_recall.py` + `tests/integration/test_memory_lifecycle.py`

**策略**:
- 直接测试：`HybridRecaller.recall()` + `FTS5Recaller` + `MemoryRecaller` → 验证返回 RecallResult（已部分有，补全）
- 端到端：`agent.run()` 前存记忆 → `run()` → 检查 `agent.context.messages` 中 system prompt 含记忆内容

**验证点**:
- `HybridRecaller.recall(query)` 返回非空且 score >= threshold
- 端到端 system prompt 注入记忆片段

### 场景 3: Memory save 全链路 (command.remember → store → memory.saved)

**测试文件**: `tests/integration/test_memory_lifecycle.py`
**策略**: `agent.hooks.emit("command.remember", text="...", key="...")` → 验证 `store.load(key)` 有记录 + `memory.saved` 事件被触发

**验证点**:
- store 中 key 对应 value 正确
- tags 包含 `[user]`
- `memory.saved` 事件被触发（通过 hook handler 计数）

### 场景 4: RecoveryPipeline 重试

**测试文件**: `tests/integration/test_scenarios.py`
**策略**: MockLLMClient 第一次调用抛 500 → RecoveryPipeline 重试 → 第二次调用返回成功

**验证点**:
- 第一次 `llm.chat` 抛出异常后，第二次调用成功
- 最终 `agent.run()` 返回成功响应（不因首次异常崩溃）

### 场景 5: Hook 事件 during loop

**测试文件**: `tests/observability/test_observer.py`
**策略**: `agent.run()` 触发后，验证 `llm.chat` / `tool.after_execute` / `conversation.turn` 事件被触发（通过自定义 hook handler 计数）

**验证点**:
- `llm.chat` 事件至少 1 次
- `tool.after_execute` 事件次数匹配 tool 调用次数
- `conversation.turn` 事件 = 轮次

### 场景 6: MCP tool calling E2E

**测试文件**: `tests/integration/test_scenarios.py`
**策略**: Mock MCP server → `agent.run()` 触发 MCP tool call → 验证 tool result 正确

**验证点**:
- MCP tool call 被触发
- tool result 正确注入 LLM 下一轮消息
- agent 最终响应包含 tool 结果

## 测试文件分布

```
tests/integration/test_scenarios.py        +5 tests (压缩/fork/recovery/recall_e2e/mcp_e2e)
tests/integration/test_memory_lifecycle.py +2 tests (recall注入端到端/save事件)
tests/memory/test_recall.py               +3 tests (HybridRecaller/FTS5/MemoryRecaller 直接)
tests/observability/test_observer.py      +1 test  (hook事件计数)
```
**合计: ~11 个新测试**

## Mock 策略

- 全部使用 `MockLLMClient` 和 `StreamingMockLLMClient`（不调真实 API）
- 工具用 `conftest.py` 的 `MockEchoTool` / `MockReadTool` / `MockBashTool`
- Session store 用 `tmp_path` fixture（临时文件，自动清理）
- MCP 用 `tests/mcp/test_manager.py` 已有 mock server 模式

## 不在本 spec 范围

- Guard 测试修复（API drift，`assert result is True` vs `assert result == GuardResult`）
- CLI 命令 REPL 层测试（需要 subprocess fixture）
- 真实 LLM 调用（成本高，CI 不友好）

## 扩展点

- 后续可加：压缩后 token 计数验证、fork 后 context 一致性验证