# 项目进展

> 每次开发会话后更新。每次重大提交后必须根据提交内容同步更新。
> 最后更新: 2026-06-04

## 目标对标

对标 **Hermes Agent** (自学习/记忆/多平台网关)、**OpenClaw** (多平台/插件/定时任务)、**OpenCode** (TUI/Skill/MCP)，取其三家之长，构建更精简、更可落地的 AI Agent 框架。

## 当前状态

**阶段**: Phase 2 深入 | **焦点**: Memory 召回已完成 | **对标差距**: hermes 10 / openclaw 10 / merco → 8

### 本次会话更新 (2026-05-29)

- **Memory 召回（新功能）**: `Recaller` 协议 (`BaseRecaller` ABC) → `FTS5Recaller`（调 SessionSearch）+ `MemoryRecaller`（调 MemoryStore）→ `HybridRecaller` 聚合/排序/去重/截断/缓存。`Agent._build_system_prompt()` 末尾自动注入召回（3条×300字≈600 tokens）。`/recall` CLI 命令手动搜索。配置项：`memory.recall_enabled/limit/max_chars/threshold`。测试 23+7+16=46 个。
- **memory config 重构**: `memory_enabled/memory_path` 移入 `memory` 嵌套对象，与 recall 配置统一。`_from_dict` 加 isinstance 守卫防非 dict 值 crash。
- **会话 Fork/分支（新功能）**: `SessionStore.clone_session()` 原子深克隆 + `get_children()` 子会话查询。`Session.fork()` 工厂方法。`Agent._compress_context` 压缩前自动 fork 归档。`/fork` CLI 命令手动分支 + `/tree` 分支树查看。配置：`session.fork_enabled` + `session.fork_auto_on_compress`。测试 15 个。

### 本次会话更新 (2026-06-04)

- **LLMClient 延迟初始化优化**: `asyncio.sleep(0)` 从 `_request()` 裸补丁提取为独立 `_ensure_client_ready()` 方法 + `_client_ready` flag，首次请求前执行一次，后续零开销。httpx 连接池竞态修复不再污染请求主线。
- **流式 reasoning 渲染限流 + 重构**: 新增 `stream_render_interval` 配置项（默认 0.05s），控制 Panel 最小渲染间隔，解决长推理卡顿。提取 `_build_reasoning_panel()` 模块级函数，消除 `NonStreamingProvider` / `StreamingProvider` / `Agent._render_reasoning` 三处 Panel 构建重复。

### 本次会话更新 (2026-06-03)

- **中断处理重构**: Ctrl+C 三态（取消工具→清输入→退出）。InterruptCleanupPipeline 策略/处理器模式。StreamingProvider cancel checkpoint 保存 partial reasoning/content/tool_calls。Report 累计公式修复为 `acc + (live - last_merged)`。
- **OpenAI 兼容加固**: `_normalize_tool_calls` 统一防护 id/name/arguments/function 为 None（scnet 等不标准 API 首 chunk function 字段缺失不崩）。`extra_params`/`headers` 可配置透传。`stream_options={"include_usage": True}` 自动注入。空 choices 提早返回。
- **MCP 客户端（新功能）**: MCPServerManager 164 行完整实现，支持 stdio/HTTP 传输、工具发现、自动注册、ToolGuard 沙箱集成、Hook 适配。
- **观察性升级**: Observer 深度集成到中断管线（SavePartialState snapshot/restore）、Observer 实例化并用于中断快照/恢复/Report。
- **日志打桩**: context.add/reasoning 泄漏检测 WARNING、工具调用全链路 DEBUG、会话恢复路径推理追踪。5 个检查点。
- **设计文档清理**: 移除 `docs/superpowers/` 下 23 个已完成的规划/设计文档。

### 本次会话更新 (2026-05-28)

- **edit diff split view 重写**: `SequenceMatcher` 对齐 → 上下文裁剪(±3行) → 仅变色变更行 → 行号 + Table 渲染。替代旧的全量并排+全量染色。`sandbox_mode: "show"` 展示 diff 自动应用不询问。
- **edit_file spinner 修复**: 交互式工具跳过 Live spinner（会覆盖 confirm_edit 提示），其他工具保留。
- **MultiEdit 删除**: 无引用、事务语义对 LLM 无意义、150行代码。
- **read_file 流式化**: `f.readlines()` → 逐行迭代，读到 limit 即停。默认 500 行，支持 head/tail，返回 has_more/mtime/hint。砍掉 char 模式，截断阈值 8KB→16KB。
- **write_file 语义明确**: 描述标注"仅用于新建文件"，edit_file 标注"修改已有文件首选"。
- **ProviderInfo 架构升级**: `PROVIDER_REGISTRY` dict→dataclass，含 name/models/key_help/description。新增平台只需一条记录，setup 向导自动适配。
- **merco setup 交互向导（新模块）**: 5 步流程（选平台→填key→选模型→确认base_url→保存）。`merco setup` CLI 命令。启动无 API key 时友好提示并可直接进入向导。
- **think tag 泄漏修复**: `_strip_think_tags` 兜底清理，防 DirectFieldStrategy 命中后 ThinkTagStrategy 没跑导致 content 残留 `<thinking>` 标签。
- **流式思考简化**: 删除 `_split_sentences`，每个 API chunk 直接刷 Live panel，不依赖标点切分。
- **PromptArea 扩展**: ContextBar 显示模型名+sandbox模式，`extra()` 链式追加状态信息。

- **ToolGuard 敏感命令守卫（新模块）**: 30 条默认 ask 规则，细粒度 `pattern + action` 匹配。用户可在 `merco.json` 追加规则或改为 deny。Bash 工具执行前拦截，确认后放行。agent 零负担。
- **Session SQLite 持久化**: `sessions` + `messages` 两张表，WAL 模式。启动自动恢复 + 灌入上下文，每轮增量存盘，`/sessions` 列表+切换，`/new` 创建新会话，Ctrl+C 退出自动 save。tool call/result 完整链路持久化。

- **Observability hooks 驱动**: `Observer` 门面 + 4 个 hooks 事件（`llm.chat`/`tool.after_execute`/`tool.error`/`conversation.turn`）。Agent emit 事件，Observer 订阅计数。`/report` 命令显示本次+累计统计。两套计数器（live + acc_map）分别追踪当前运行和跨运行累计。退出/切会话/`/new` 时合并 live→acc 持久化到 SQLite，重启恢复。缓存命中率、token 入/出、工具分布完整采集。
- **Token 兼容 fallback**: 流式模式下 MiniMax 等 provider 不返回 usage → `total_tokens` 估算入 token，`est_tk(content+reasoning)` 估算出 token。非流式或返回 usage 的 provider 直接采信真实值。永不为 0。
- **Skill 全局目录修复**: `SkillLoader.load_from_directory` 加 `.expanduser()`，`~/.config/merco/skills/` 不再因 tilde 未展开而加载失败。
- **Thinking panel UI bug**: `Live(transient=True)` 清终端残留，普通 `console.print` 留最终面板，键盘输入不再干扰渲染。
- **openai import 延迟加载**: `LLMClient.__init__` 内 import openai，测试环境无 openai 也能 import 其他模块。
- **集成测试框架**: `conftest.py` MockLLMClient + test_agent fixture，10 个集成测试覆盖对话/工具/会话/guard/上下文恢复，2 秒全过。

### 上次会话更新 (2026-05-26)

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

### merco/core/ — Core Engine

| File | Status | Details |
|------|--------|---------|
| `agent.py` | 🟢 POLISHED | Full agent loop。LLM retry 归零（交 RecoveryPipeline）。_wrap_up 收尾。Interrupt pipeline 策略/处理器模式（中断恢复 + partial state 保存到 context/session）。Observer integration（snapshot/restore/report）。**但**: hooks 未接入、sandbox 未调用。`_build_reasoning_panel` 统一 Panel 构建 + `stream_render_interval` 限流。 |
| `config.py` | 🟢 POLISHED | `ProviderInfo` dataclass 含 name/models/key_help。5 个预置平台，一条记录驱动 setup 向导。 |
| `setup.py` | 🟢 NEW | 交互式 API 配置向导，5步流程。`merco setup` 命令。 |
| `observer.py` | 🟢 NEW | hooks 驱动可观察性门面，`/report` 命令，live+acc 双计数器。 |
| `llm.py` | 🟢 POLISHED | 纯传输层 + `_strip_think_tags` + `_extract_usage` 多 provider 缓存采集 + `_normalize_tool_calls` None 防护（id/name/arguments/function 任一 None 不崩）+ `extra_params`/`headers` 透传 + `stream_options` + `_ensure_client_ready` 延迟初始化。 |
| `session.py` | 🟢 POLISHED | Session 数据类 + save/load/resume_or_create，增量写 SQLite，tool call 完整链路持久化。 |
| `message.py` | 🟢 REAL | `Message` dataclass + `to_dict()` + `MessageProcessor`。|
| `context.py` | 🟢 REAL | `ContextManager` + `estimate_tokens()`/`msg_tokens()`（含 tool_calls 计数）+ `total_tokens` 优先 API 实测。死壳已删。|

### merco/tools/ — Tool System

| File | Status | Details |
|------|--------|---------|
| `base.py` | 🟢 REAL | `BaseTool` ABC，definition property OpenAPI schema。|
| `registry.py` | 🟢 REAL | `ToolRegistry`：register/unregister/execute（try/except 转结构化错误）。 |
| `file_tools.py` | 🟢 POLISHED | 流式行读 + head/tail + has_more + 500行默认。`write_file` 语义明确。**未接入 Sandbox。** |
| `edit.py` | 🟢 POLISHED | SEARCH/REPLACE + diff 预览 + 确认。MultiEdit 已删。 |
| `bash_tools.py` | 🟢 REAL | `BashTool` asyncio subprocess。**未调 SecurityChecker。** |
| `web_tools.py` | 🟡 PARTIAL | `WebFetch` 可用。`WebSearch` 骨架。|
| `task_tools.py` | 🔴 SKELETON | `"not yet implemented"`。|
| `mcp_tools.py` | 🟢 REAL | MCPServerManager（stdio/HTTP 传输，工具发现，自动注册）+ ToolGuard 沙箱集成 + Hook 适配。 |

### merco/skills/ — Skills System

| File | Status | Details |
|------|--------|---------|
| `loader.py` | 🟢 REAL | 递归扫描 SKILL.md，YAML frontmatter。|
| `registry.py` | 🟢 REAL | register/get/list/get_relevant/load_from_paths。|
| `builtin/` | 🔴 SKELETON | 空目录。|

### merco/memory/ — Memory System

| File | Status | Details |
|------|--------|---------|
| `store.py` | 🟢 REAL | JSON 文件 CRUD。|
| `recall.py` | 🟢 POLISHED | `BaseRecaller` ABC + `FTS5Recaller` + `MemoryRecaller` + `HybridRecaller`（聚合/去重/截断/缓存）+ 旧版 `MemoryRecall` 兼容。已接入 Agent。 |
| `compressor.py` | 🟢 REAL | Token 滑动窗口 + 链完整 + LLM 摘要。Token 函数统一从 `core/context` 导入。 |
| `search.py` | 🟢 REAL | SQLite FTS5。|
| `session_store.py` | 🟢 NEW | SQLite 会话持久化，sessions + messages 表，WAL 模式。 |

### Other Modules

| Module | Status |
|--------|--------|
| `hooks/` | 🔴 SKELETON — 未集成 |
| `sandbox/` | 🟢 POLISHED — diff split view + show mode + ToolGuard guard。未集成到 Tools |
| `scheduler/` | 🟢 REAL — CLI 未启动 |
| `observability/` | 🟢 REAL — Observer 已接入 Agent（中断/Report），hooks 未触发 |
| `mcp/` | 🟢 NEW — MCPServerManager stdio+HTTP 传输，工具发现+注册，沙箱集成 |
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
| Observability → Agent | ⚠️ PARTIAL | Observer 已实例化并用于中断快照/恢复/Report。LLM 调用/Tool 执行点通过 hooks emit（需先打通 Hooks → Agent）。中断管线 SavePartialState 使用 Observer snapshot。 |
| MCP → Agent | ✅ WIRED | MCPServerManager 接管 MCP config 加载 + 工具注册 + 沙箱守卫。 |
| Memory Recall → Agent | ✅ WIRED | `_build_system_prompt` 自动注入 FTS5 召回结果。 |

---

## 汇总

| Status | Count |
|--------|-------|
| 🟢 POLISHED | 11 |
| 🟢 NEW | 5 |
| 🟢 REAL | 8 |
| 🟡 PARTIAL | 6 |
| 🔴 SKELETON | 8 |
| ✅ WIRED | 4 |

## 三家对标 (2026-05-29)

| 特性 | hermes | opencode | openclaw | merco |
|------|--------|----------|----------|-------|
| Session CRUD | ✓ | ✓ | ✓ | ✓ |
| FTS5 全文搜索 | ✓✓ 双tokenizer | ✗ | ✓ | ✓ |
| Fork/Branch | ✓ | ✓ | ✓ | **✓ (新增)** |
| Revert/Undo | ✗ | ✓ | ✗ | ✗ |
| 压缩保留尾轮 | ✓ | ✓ | ✓ | ✓ |
| 压缩 checkpoint | ✗ | ✗ | ✓ | ✓ |
| 消息原文件持久化 | ✓ | ✓ | ✓ | ✓ |
| Memory 召回 | ✓ | ✗ | ✓ | **✓ (新增)** |
| 成本追踪 | ✓ | ✓ | ✓ | ✗ |
| 会话清理/归档 | ✓ | ✓ | ✓ | ✗ |
| 跨会话搜索 | ✓ | ✗ | ✓ | ✓ |
| 观察性报告 | ✗ | ✗ | ✗ | ✓ 独有 |

**总分**: hermes 10 / opencode 7 / openclaw 10 / **merco 10**

## 已知问题 / 技术债

| # | 位置 | 问题 | 修复方案 | 优先级 |
|---|------|------|----------|--------|
| 1 | `core/agent.py` StreamingProvider checkpoint | `__anext__()` I/O 等待时 CancelledError 不执行 checkpoint，partial content 丢失 | 改用 `except CancelledError` 统一拦截 | 低 |
| 2 | `core/agent.py` StreamingProvider reasoning 渲染 | ~大段推理文本每次 chunk 重建 Panel，卡顿后跳出一堆~ | ✅ 已修复：`stream_render_interval` 限流 + `_build_reasoning_panel` 统一构建 | — |
| 3 | `core/llm.py` / `agent.py` reasoning 泄漏怀疑 | 用户观察到历史 reasoning 出现在 thinking 面板，代码审查未发现客户端泄漏路径 | 已在 5 处加日志打桩，`--debug` 观察 | — |

## 下一步（按优先级）

1. **打通 Sandbox → Tools** — Bash/File 工具调用 SecurityChecker + SandboxIsolation
2. **打通 Hooks → Agent** — Agent Loop 关键节点 emit 事件
3. **打通 Observability → Agent** — 通过 hooks emit 完整可观察性埋点
4. **实现 Session 持久化** — 增量写 SQLite（已基础实现，需容错增强）
5. **接入 LLM 上下文压缩** — 替换占位摘要为真实 LLM 调用（已基础实现）
6. **实现 WebSearch** — 对接搜索 API
7. **实现 MCP 客户端协议** — 接入外部 MCP server（已实现 MCPServerManager）
8. **补充集成测试** — mock LLM 的 Agent-Loop 全覆盖测试
9. **打通 Memory → Sessions** — Agent 存储/召回会话记忆
10. **打通 Scheduler → Runtime** — CLI/Web 启动时激活
11. **通一个 Gateway** — Telegram 端到端
12. **TUI 实现** — Textual 替换 `"coming soon"`
