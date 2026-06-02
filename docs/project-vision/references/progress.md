# 项目进展

> 每次开发会话后更新。每次重大提交后必须根据提交内容同步更新。
> 最后更新: 2026-06-03 (v0.2.0 集成完成)

## 目标对标

对标 **Hermes Agent** (自学习/记忆/多平台网关)、**OpenClaw** (多平台/插件/定时任务)、**OpenCode** (TUI/Skill/MCP)，取其三家之长，构建更精简、更可落地的 AI Agent 框架。

## 当前状态

**阶段**: Phase 2 深入 → v0.2.0 发布 | **焦点**: 关键集成链路打通、Provider 可扩展、Session 持久化、可观察性

### 本次会话更新 (2026-06-03)

- **Skill 同步**: 三个 skill 副本 (`.merco/`、`.opencode/`、`.reasonix/`) 与源 `docs/project-vision/` 内容对齐。移除过期 OpenMercury 命名，状态计数重算为三状态（REAL/PARTIAL/SKELETON + NOT WIRED）。
- **代码-文档对齐**: 验证实际代码状态，标记 `.merco/skills` 副本中描述但未实现的 Recaller/Fork 体系为"Phase 5 计划中"。

### v0.2.0 发布 (2026-05-31) — Observer+hooks+SessionStore+Token fallback+集成测试

**关键集成 (3 条链从 ❌ NOT WIRED 转为 ✅ WIRED)**：
- **Hooks → Agent**: `HookRegistry` (4 事件: `llm.chat`/`tool.after_execute`/`tool.error`/`conversation.turn`) + `Observer` 门面 (双计数器 live+acc_map)。
- **Sandbox → Tools**: `ToolGuard` 30 条默认 ask 规则链，按 pattern 匹配，user 可在 `merco.json` 追加。
- **Observability → Agent**: Agent 在 `_execute_tool_calls` 和 LLM 调用点 `await self.hooks.emit(...)`，Observer 订阅计数。

**新模块 (3 个)**：
- `merco/observability/observer.py` (139 行) — hooks 驱动可观察性门面
- `merco/sandbox/guard.py` (166 行) — ToolGuard 规则链
- `merco/memory/session_store.py` (175 行) — SQLite 持久化 (sessions + messages 表, WAL 模式, 增量写)

**架构升级 (4 项)**：
- **ProviderInfo dataclass**: `PROVIDER_REGISTRY` dict → dataclass，含 name/models/key_help/description/默认 base_url。新增平台只需一条记录。
- **`merco setup` 交互向导**: 5 步流程（选平台→填 key→选模型→确认 base_url→保存）。`merco setup` CLI 命令。启动无 API key 时友好提示。
- **Observer 累计公式**: `acc + (live - last_merged)` —— 三容器各司其职（acc 锚点 / live 实时 / last_merged 合并快照）。
- **Token 兼容 fallback**: 流式模式下 MiniMax 等 provider 不返回 usage → `total_tokens` 估算入 token，`est_tk(content+reasoning)` 估算出 token。非流式或返回 usage 的 provider 直接采信真实值。永不为 0。

**UI 改进 (4 项)**：
- **edit diff split view 重写**: `SequenceMatcher` 对齐 → 上下文裁剪(±3 行) → 仅变色变更行 → 行号 + Table 渲染。`sandbox_mode: "show"` 展示 diff 自动应用不询问。
- **read_file 流式化**: `f.readlines()` → 逐行迭代，读到 limit 即停。默认 500 行，支持 head/tail，返回 has_more/mtime/hint。截断阈值 8KB→16KB。
- **edit_file spinner 修复**: 交互式工具跳过 Live spinner（会覆盖 confirm_edit 提示），其他工具保留。
- **think tag 泄漏修复**: `_strip_think_tags` 兜底清理，防 DirectFieldStrategy 命中后 ThinkTagStrategy 没跑导致 content 残留。

**Session/CLI 改进 (3 项)**：
- **Session SQLite 持久化**: `SessionStore` 两张表 WAL 模式。启动自动恢复 + 灌入上下文，每轮增量存盘。tool call/result 完整链路持久化。
- **Provider 架构升级**: `ProviderInfo` 含 5 个预置平台（openai/minimax/anthropic/openrouter/deepseek）。新平台一行注册。
- **openai import 延迟加载**: `LLMClient.__init__` 内 import openai，测试环境无 openai 也能 import 其他模块。

**测试 (3 项)**：
- **集成测试框架**: `conftest.py` MockLLMClient + test_agent fixture，覆盖对话/工具/会话/guard/上下文恢复。
- **`/report` 命令**: 显示本次 + 累计统计（缓存命中率、token 入/出、工具分布）。
- **退出/切会话/`/new` 时合并 live→acc**: 持久化到 SQLite，重启恢复。

### Phase 1 收尾 (2026-05-26) — 架构清理

- **启动首页 Dashboard**: 可组合架构（`DashboardSection` ABC + `WelcomeSection`/`ModelSection`/`ToolsSection`/`SkillsSection`/`ConfigSection`/`HintSection`/`SessionSection`），新增条目只需继承 + `dashboard.use()`。
- **输入区 PromptDecorator**: `PromptArea` + `ContextBar`（16 格半高薄款），删工具计数，`▸` 提示符。
- **LLMClient 去重 + 统一策略**: `_build_params()` + `_request()` 提取，`chat()` 40 行→4 行，`chat_stream()` 40 行→5 行。retry 从 LLM 层移到 Agent RecoveryPipeline（唯一重试点）。`llm.py: 330 行→200 行`。
- **Token 估算统一**: 删 `compressor.py` 重复的 `count_tokens()`/`msg_tokens()`；合并到 `core/context.py`。
- **Token 账本修复**: `msg_tokens()` 补 tool_calls JSON 计数；`total_tokens` 优先 API 实测 `last_actual_tokens`。
- **`_is_retryable_llm_error` 悬空引用修复**: 删不存在 `_is_transient_429`；改状态码大类 (429+5xx) + 消息关键字兜底。
- **`_execute_tool_calls` 防护**: `json.dumps()` 包 try/except 防非可序列化对象穿透到 LLM 恢复管线。
- **`TimeContextChunk`**: PromptBuilder 新 chunk，注入当前时间到 system prompt。
- **清理死代码**: `context.py` 删死壳 `ContextCompressor` + `__init__` 重复赋值；`self_healing.py` 删 `llm_error()` 噪音 WARNING。

## 里程碑

- [x] Phase 0: 项目初始化与 vision skill 创建
- [x] Phase 1: 核心 Agent-Loop 与基础工具
- [x] Phase 2a: 关键集成链路打通（Hooks/Sandbox/Observability）— **v0.2.0**
- [x] Phase 2b: Session 持久化 + Provider 架构 + setup 向导
- [ ] Phase 3: Skill 系统完善 + MCP 集成
- [ ] Phase 4: TUI 与 Web 界面
- [ ] Phase 5: Memory 召回体系 + Session Fork/Tree + 多代理协作
- [ ] Phase 6: 可观测性深化（tracing/metrics 可视化）+ 沙箱容器化
- [ ] Phase 7: 文档、测试与发布

---

## 模块逐项审计

### merco/core/ — Core Engine

| File | Status | Details |
|------|--------|---------|
| `agent.py` | 🟢 REAL | Full agent loop。Hooks 4 事件 emit、Observer 订阅、ToolGuard 拦截、SessionStore 持久化、_wrap_up 收尾、PromptBuilder+3 chunks、Pipeline (Result/Recovery/EmptyResponse) 完整集成。681 行。 |
| `config.py` | 🟢 REAL | `MercoConfig` + `ModelConfig` + `ProviderInfo` dataclass。5 个预置平台（openai/minimax/anthropic/openrouter/deepseek）。`ProviderInfo.__getitem__` 向后兼容 dict-style 访问。`resolve()` 自动补 base_url/api_key。226 行。 |
| `setup.py` | 🟢 REAL | 交互式 API 配置向导，5 步流程。`merco setup` CLI 命令。192 行。 |
| `llm.py` | 🟢 REAL | OpenAI 兼容异步客户端。`_build_params` + `_request` 提取，`chat`/`chat_stream` 共享。`_strip_think_tags` 兜底、`_extract_usage` 多 provider 缓存采集。openai import 延迟。~430 行。 |
| `session.py` | 🟢 REAL | Session 数据类 + save/load/resume_or_create。增量写 SQLite，tool call 完整链路持久化。`fork()` **未实现**（Phase 5）。90 行。 |
| `message.py` | 🟢 REAL | `Message` dataclass + `to_dict()` + `MessageProcessor`。 |
| `context.py` | 🟢 REAL | `ContextManager` + `estimate_tokens`/`msg_tokens`（含 tool_calls 计数）+ `total_tokens` 优先 API 实测。`compress()` **未实现**（Phase 6 走 LLM 摘要）。 |
| `pipeline.py` | 🟢 REAL | `ResultPipeline` + `RecoveryPipeline` + `EmptyResponsePipeline`，链式 use()/process()。含 `TruncationProcessor`(16KB)/`SkillViewProcessor`/`WaitRecovery`/`ContextCompressRecovery`/`CallbackEmptyResponse`。573 行。 |
| `self_healing.py` | 🟢 REAL | 恢复管线实现，LLM 错误分类与重试。 |

### merco/tools/ — Tool System

| File | Status | Details |
|------|--------|---------|
| `base.py` | 🟢 REAL | `BaseTool` ABC，`definition` property OpenAPI schema。 |
| `registry.py` | 🟢 REAL | `ToolRegistry`：register/unregister/execute（try/except 转结构化错误）。 |
| `__init__.py` | 🟢 REAL | `discover_tools()` 自动发现 7 个内置工具 + 扫描外部路径。 |
| `file_tools.py` | 🟢 REAL | 流式行读 + head/tail + has_more + 500 行默认。`write_file` 语义明确。**ToolGuard 集成由 agent.py 完成**。 |
| `edit.py` | 🟢 REAL | SEARCH/REPLACE + diff 预览 + 确认。SequenceMatcher split view，sandbox_mode: "show" 自动应用。MultiEdit 已删。125 行。 |
| `bash_tools.py` | 🟢 REAL | `BashTool` asyncio subprocess。**ToolGuard 集成由 agent.py 完成**。 |
| `skill_tools.py` | 🟢 REAL | `SkillViewTool` 动态描述（列出可用技能）+ `check()` 有技能才显示。73 行。 |
| `web_tools.py` | 🟡 PARTIAL | `WebFetch` 可用 (httpx + HTML strip)。`WebSearch` 骨架（"not yet configured"）。 |
| `task_tools.py` | 🔴 SKELETON | `"not yet implemented"`，无子代理派发逻辑。Phase 5。 |
| `mcp_tools.py` | 🔴 SKELETON | `"not yet configured"`。Phase 3。 |

### merco/skills/ — Skills System

| File | Status | Details |
|------|--------|---------|
| `loader.py` | 🟢 REAL | 递归扫描 SKILL.md，YAML frontmatter。`load_from_directory` 加 `.expanduser()`。 |
| `registry.py` | 🟢 REAL | register/get/list/get_relevant/load_from_paths。 |
| `builtin/` | 🔴 SKELETON | 空目录。 |

### merco/memory/ — Memory System

| File | Status | Details |
|------|--------|---------|
| `store.py` | 🟢 REAL | `MemoryStore`：JSON 文件 CRUD + tag + 文本匹配搜索。 |
| `recall.py` | 🟢 REAL | `MemoryRecall`：关键词召回 + `get_relevant_context()`。**Recaller 协议 (BaseRecaller/FTS5Recaller/HybridRecaller) 未实现**（Phase 5）。 |
| `search.py` | 🟢 REAL | `MemorySearch`：SQLite FTS5 全文索引。 |
| `compressor.py` | 🟡 PARTIAL | Token 滑动窗口 + 链完整。LLM 摘要为占位文本（`_summarize` 未调真实 LLM）。Phase 6。 |
| `session_store.py` | 🟢 REAL | SQLite 会话持久化，sessions + messages 表，WAL 模式。**`clone_session()`/`get_children()` 未实现**（Phase 5 Session Fork）。175 行。 |

### merco/hooks/ — Hook System

| File | Status | Details |
|------|--------|---------|
| `registry.py` | 🟢 REAL | `HookRegistry`：on/off/emit/clear，检测 async/sync handler。**Agent 已使用**。 |
| `lifecycle.py` | 🟡 PARTIAL | 注册 4 个 hook 点 (`agent.start/stop`, `session.create/destroy`)，handler 仍为 `pass`。 |
| `chat_hooks.py` | 🟡 PARTIAL | 注册 3 个 hook 点 (`message.receive/send`, `context.compact`)，handler 仍为 `pass`。 |
| `tool_hooks.py` | 🟡 PARTIAL | 注册 3 个 hook 点 (`tool.before/after/error`)，handler 仍为 `pass`。 |

### merco/sandbox/ — Sandbox/Security

| File | Status | Details |
|------|--------|---------|
| `guard.py` | 🟢 REAL | `ToolGuard`：30 条默认 ask 规则，pattern + action 链式匹配。**Agent 已使用**。166 行。 |
| `confirm.py` | 🟢 REAL | edit_file 确认交互。 |
| `isolation.py` | 🟢 REAL | `SandboxIsolation`：临时目录创建/白名单/只读/穿越检测/清理。 |
| `permissions.py` | 🟢 REAL | `PermissionManager`：allow/ask/deny 模式，fnmatch 规则。 |
| `security.py` | 🟢 REAL | `SecurityChecker`：正则危险命令检测 + 路径穿越保护。 |
| `snapshot.py` | 🟢 REAL | 文件快照追踪（edit_file 写前备份）。 |

### merco/observability/ — Observability

| File | Status | Details |
|------|--------|---------|
| `observer.py` | 🟢 REAL | Observer 门面：hooks 订阅 + 双计数器 (live+acc_map) + snapshot/restore/report。**Agent 已使用**。139 行。 |
| `metrics.py` | 🟢 REAL | `MetricsCollector`：counter/timing/event/average/summary。 |
| `audit.py` | 🟢 REAL | `AuditLogger`：JSON-lines 追加 + 限额读取。 |
| `tracing.py` | 🟢 REAL | `TraceSpan` + `Tracer`：创建/结束/属性/耗时/ContextVar trace ID。 |
| `logger.py` | 🟢 REAL | `setup_logger()`：Python logging，console + 可选 file。 |

### merco/scheduler/ — Scheduler

| File | Status | Details |
|------|--------|---------|
| `cron.py` | 🟢 REAL | `CronScheduler`：CronJob dataclass，add/remove/list，start 轮询 (60s)，stop。 |
| `jobs.py` | 🟢 REAL | `TaskManager` + `Task` dataclass：create/get/update_status。 |
| `delivery.py` | 🟢 REAL | `DeliveryManager`：注册/投递渠道。 |
| **集成** | ❌ NOT WIRED | CLI/Web 未启动 Scheduler。 |

### merco/gateway/ — Message Gateways

| File | Status | Details |
|------|--------|---------|
| `base.py` | 🟢 REAL | `BaseGateway` ABC：`set_handler`/`handle_message`，抽象 start/stop/send_message。 |
| `telegram.py` | 🔴 SKELETON | 所有方法为 `pass` + `# TODO: 集成...`。 |
| `discord.py` | 🔴 SKELETON | 同上。 |

### cli/ — CLI Interface

| File | Status | Details |
|------|--------|---------|
| `main.py` | 🟢 REAL | Full Typer CLI：`run` (REPL，async input，Dashboard，Pipeline 集成) + `init` + `skills` + `setup`。`/help`/`/exit`/`/new`/`/model`/`/tools`/`/sessions`/`/report` 可用。 |
| `tui.py` | 🔴 SKELETON | `"TUI mode - coming soon"`。无 Textual/Rich 实现。 |
| `commands.py` | 🔴 SKELETON | 仅注释 `# 命令将在 main.py 中统一定义`。`/recall`/`/fork`/`/tree` 命令 **Phase 5**。 |

### web/ — Web Interface

| File | Status | Details |
|------|--------|---------|
| `app.py` | 🟡 PARTIAL | FastAPI app：`/` (version)、`/health` (ok)、`/chat` (返回 `"coming soon"`)。未对接 Agent。 |

### tests/

| File | Status | Details |
|------|--------|---------|
| `conftest.py` | 🟢 REAL | MockLLMClient + test_agent fixture。 |
| `test_guard.py` | 🟢 REAL | ToolGuard 规则链测试。 |
| `test_session.py` | 🟢 REAL | Session CRUD 测试。 |
| `integration/test_agent_loop.py` | 🟢 REAL | Agent-Loop 端到端测试。 |
| `integration/test_scenarios.py` | 🟢 REAL | 场景测试。 |
| `unit/test_session.py`, `test_tools.py`, `test_config.py` | 🟢 REAL | 单元测试。 |

---

## Cross-Cutting Wiring Checks

| Integration | Verdict | Details |
|-------------|---------|---------|
| **Hooks → Agent** | ✅ WIRED | `agent.py:221-224` 实例化 `HookRegistry`+`Observer`，4 事件 emit (llm.chat, tool.after_execute, tool.error, conversation.turn)。Observer 订阅计数。 |
| **Sandbox → Tools** | ✅ WIRED | `agent.py:227-231, 474-476` 实例化 `ToolGuard`，`_execute_tool_calls` 前 `await self.guard.check()`。30 条默认 ask 规则链。 |
| **Observability → Agent** | ✅ WIRED | Observer 双计数器 (live+acc_map)。`/report` 命令显示本次+累计统计。重启从 SQLite 恢复 acc。 |
| **SessionStore → Agent** | ✅ WIRED | `agent.py:234-236` 实例化 `SessionStore`，`Session.resume_or_create` 自动恢复，每轮 `session.save()`。`~/.merco/sessions.db`。 |
| **Memory → Sessions** | ❌ NOT WIRED | SessionStore 仅存消息，MemoryStore 仍是独立模块。Agent.run 不调 `MemoryStore.save()` 或 `MemoryRecall.recall()`。Phase 5 计划中。 |
| **Scheduler → Runtime** | ❌ NOT WIRED | CLI/Web 未启动 CronScheduler。代码完整但从未激活。 |
| **Skills → Agent** | ⚠️ PARTIAL | `SkillRegistry` + `SkillViewTool` + `SkillsHintChunk` 全链路完整。`get_relevant()` keyword 匹配未注入到 PromptBuilder。 |

---

## 汇总

| Status | Count | 说明 |
|--------|-------|------|
| 🟢 REAL (可用) | 24 | 生产级或基本可用的独立模块 |
| 🟡 PARTIAL (部分) | 6 | 核心可用但有关键功能缺失（web_search/context.compress/compressor LLM 摘要/3 个 hooks handlers 仍 pass/web/app.py） |
| 🔴 SKELETON (骨架) | 8 | mcp_tools, task_tools, scheduler, tui, 2 个 gateway, builtin/skills, commands.py |
| ❌ NOT WIRED (未集成) | 3 | Memory → Sessions, Scheduler → Runtime, Memory 嵌套配置 + Recaller 协议（Phase 5 计划中） |

## 下一步（按优先级）

### Phase 3（Skill 系统完善 + MCP 集成）
1. **实现 MCP 客户端协议** — `mcp_tools.py` 替换 `"not yet configured"`
2. **SkillViewTool 增强** — 支持分片加载 + 缓存
3. **builtin/skills 填充** — 内置项目级 skill 文档

### Phase 4（TUI 与 Web 界面）
4. **TUI 实现** — Textual 替换 `"coming soon"`
5. **Web 对接 Agent** — `app.py` 接入 Agent + 会话管理
6. **WebSearch 实现** — 对接搜索 API

### Phase 5（Memory 召回 + Session Fork + 多代理）
7. **Recaller 协议体系** — `BaseRecaller` ABC + `FTS5Recaller` + `MemoryRecaller` + `HybridRecaller`
8. **Session Fork/Tree** — `SessionStore.clone_session()` + `get_children()` + `/fork` + `/tree` 命令
9. **Memory 嵌套配置重构** — `memory.recall_enabled/limit/max_chars/threshold`
10. **`/recall` CLI 命令** — 手动搜索记忆
11. **打通 Memory → Sessions** — Agent 自动 save/recall

### Phase 6（可观测性 + 沙箱容器化）
6. **LLM 摘要上下文压缩** — 替换 `compressor.py` 占位为真实 LLM 调用
7. **Hooks 处理器填充** — lifecycle/chat/tool 三个 hooks handlers 实现
8. **Sandbox 容器化** — Docker 隔离替换临时目录

### 持续
- **补充集成测试** — 真实 LLM 的端到端测试
- **Phase 7 文档/发布** — PyPI 发布 + 完整 README + 教程
