# 项目进展

> 每次开发会话后更新。每次重大提交后必须根据提交内容同步更新。
> 最后更新: 2026-05-26

## 目标对标

对标 **Hermes Agent** (自学习/记忆/多平台网关)、**OpenClaw** (多平台/插件/定时任务)、**OpenCode** (TUI/Skill/MCP)，取其三家之长，构建更精简、更可落地的 AI Agent 框架。

## 当前状态

**阶段**: Phase 2 深入 | **焦点**: 架构清理、消除重复、修复根基 bug、UI 可组合化

### 本次会话更新 (2026-05-26)

- **启动首页 Dashboard**: 可组合架构（`DashboardSection` ABC + `WelcomeSection`/`ModelSection`/`ToolsSection`/`SkillsSection`/`ConfigSection`/`HintSection`），新增条目只需继承 + `dashboard.use()`。工具/技能列出名字而非计数。
- **输入区 PromptDecorator**: `PromptArea` + `ContextBar`（16格半高薄款）、删工具计数、`▸` 提示符。新增装饰器只需继承 + `prompt_area.use()`。
- **LLMClient 去重 + 统一策略**: `_build_params()` + `_request()` 提取，`chat()` 40行→4行，`chat_stream()` 40行→5行。retry 从 LLM 层移到 Agent RecoveryPipeline（唯一重试点），删 `retry_delays` 参数。llm.py: 330行→200行。
- **Token 估算统一**: 删 `compressor.py` 重复的 `count_tokens()`/`msg_tokens()`；合并到 `core/context.py`。
- **Token 账本修复**: `msg_tokens()` 补 tool_calls JSON 计数；`total_tokens` 优先 API 实测 `last_actual_tokens`。
- **`_is_retryable_llm_error` 悬空引用修复**: 删不存在 `_is_transient_429`；改状态码大类 (429+5xx) + 消息关键字兜底。
- **`_execute_tool_calls` 防护**: `json.dumps()` 包 try/except 防非可序列化对象穿透到 LLM 恢复管线。
- **`TimeContextChunk`**: PromptBuilder 新 chunk，注入当前时间到 system prompt。
- **清理死代码**: `context.py` 删死壳 `ContextCompressor` + `__init__` 重复赋值；`self_healing.py` 删 `llm_error()` 噪音 WARNING。
- **通读审计**: 完成全部核心代码结构性分析，梳理 8 个优化点。

## 里程碑

- [x] Phase 0: 项目初始化与 vision skill 创建
- [x] Phase 1: 核心 Agent-Loop 与基础工具
- [ ] Phase 2: Skill 系统与 MCP 集成
- [ ] Phase 3: 记忆系统与上下文管理
- [ ] Phase 4: TUI 与 Web 界面
- [ ] Phase 5: 多代理协作与定时任务
- [ ] Phase 6: 可观测性与沙箱 (容器化)
- [ ] Phase 7: 文档、测试与发布

---

## 模块逐项审计

### openmercury/core/ — Core Engine

| File | Status | Details |
|------|--------|---------|
| `agent.py` | 🟢 POLISHED | Full agent loop。LLM retry 归零（交 RecoveryPipeline）。_wrap_up 收尾。`_execute_tool_calls` json.dumps 兜底。`PromptBuilder` + 3 chunks。 |
| `config.py` | 🟢 REAL | `OpenMercuryConfig` + `ModelConfig`，JSON load/save，multi-path discovery。|
| `llm.py` | 🟢 REAL | 纯传输层：`_build_params()` + `_request()`（cooldown 不含 retry）。`chat()` 4行，`chat_stream()` 5行。200行。 |
| `session.py` | 🟡 PARTIAL | `SessionStore` 全部 `NotImplementedError`（Phase 3 持久化）。|
| `message.py` | 🟢 REAL | `Message` dataclass + `to_dict()` + `MessageProcessor`。|
| `context.py` | 🟢 REAL | `ContextManager` + `estimate_tokens()`/`msg_tokens()`（含 tool_calls 计数）+ `total_tokens` 优先 API 实测。死壳已删。|

### openmercury/tools/ — Tool System

| File | Status | Details |
|------|--------|---------|
| `base.py` | 🟢 REAL | `BaseTool` ABC，definition property OpenAPI schema。|
| `registry.py` | 🟢 REAL | `ToolRegistry`：register/unregister/execute（try/except 转结构化错误）。 |
| `file_tools.py` | 🟢 REAL | `ReadFile`/`WriteFile`。**未接入 Sandbox。** |
| `bash_tools.py` | 🟢 REAL | `BashTool` asyncio subprocess。**未调 SecurityChecker。** |
| `web_tools.py` | 🟡 PARTIAL | `WebFetch` 可用。`WebSearch` 骨架。|
| `task_tools.py` | 🔴 SKELETON | `"not yet implemented"`。|
| `mcp_tools.py` | 🔴 SKELETON | `"not yet configured"`。|

### openmercury/skills/ — Skills System

| File | Status | Details |
|------|--------|---------|
| `loader.py` | 🟢 REAL | 递归扫描 SKILL.md，YAML frontmatter。|
| `registry.py` | 🟢 REAL | register/get/list/get_relevant/load_from_paths。|
| `builtin/` | 🔴 SKELETON | 空目录。|

### openmercury/memory/ — Memory System

| File | Status | Details |
|------|--------|---------|
| `store.py` | 🟢 REAL | JSON 文件 CRUD。|
| `recall.py` | 🟢 REAL | 关键词召回。|
| `compressor.py` | 🟢 REAL | Token 滑动窗口 + 链完整 + LLM 摘要。Token 函数统一从 `core/context` 导入。 |
| `search.py` | 🟢 REAL | SQLite FTS5。|

### Other Modules

| Module | Status |
|--------|--------|
| `hooks/` | 🔴 SKELETON — 未集成 |
| `sandbox/` | 🟢 REAL — 未集成到 Tools |
| `scheduler/` | 🟢 REAL — CLI 未启动 |
| `observability/` | 🟢 REAL — 未集成到 Agent |
| `gateway/` | 🔴 SKELETON |

### cli/ — CLI Interface

| File | Status | Details |
|------|--------|---------|
| `main.py` | 🟢 POLISHED | Dashboard + PromptDecorator 可组合架构。REPL 完整。 |
| `tui.py` | 🔴 SKELETON | `"coming soon"`。|

---

## Cross-Cutting Wiring Checks

| Integration | Verdict | Details |
|-------------|---------|---------|
| Skills → Agent | ⚠️ PARTIAL | `SkillRegistry` + `SkillViewTool` + `SkillViewProcessor` + `SkillsHintChunk` 全链路完整。`get_relevant()` 未接线。 |
| Retry → RecoveryPipeline | ✅ WIRED | LLM 不重试，错误上抛 → RecoveryPipeline。 |
| Hooks → Agent | ❌ NOT WIRED | 无 import，无 emit。 |
| Sandbox → Tools | ❌ NOT WIRED | Tools 未调 SecurityChecker。 |
| Observability → Agent | ❌ NOT WIRED | 无 metrics/tracing。 |
| Memory → Sessions | ❌ NOT WIRED | Session 不存 MemoryStore。 |

---

## 汇总

| Status | Count |
|--------|-------|
| 🟢 REAL | 18 |
| 🟡 PARTIAL | 7 |
| 🔴 SKELETON | 10 |
| ❌ NOT WIRED | 4 |

## 下一步（按优先级）

1. **打通 Sandbox → Tools** — Bash/File 工具调用 SecurityChecker + SandboxIsolation
2. **打通 Hooks → Agent** — Agent Loop 关键节点 emit 事件
3. **打通 Observability → Agent** — LLM 调用/Tool 执行处埋点
4. **实现 Session 持久化** — SQLite 替换 `NotImplementedError`
5. **自动注入相关 Skill** — `get_relevant()` 接线到 PromptBuilder
6. **实现 WebSearch** — 对接搜索 API
7. **实现 MCP 客户端协议**
8. **补充集成测试** — mock LLM 的 Agent-Loop 全覆盖测试
