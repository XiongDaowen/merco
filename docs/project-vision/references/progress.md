# 项目进展

> 每次开发会话后更新。每次重大提交后必须根据提交内容同步更新。
> 最后更新: 2026-05-22

## 目标对标

对标 **Hermes Agent** (自学习/记忆/多平台网关)、**OpenClaw** (多平台/插件/定时任务)、**OpenCode** (TUI/Skill/MCP)，取其三家之长，构建更精简、更可落地的 AI Agent 框架。

## 当前状态

**阶段**: Phase 1 完成 → Phase 2 起步 | **焦点**: 打通关键集成链路，补齐骨架模块

### 最近更新 (2026-05-22)
- **Architecture**: `_ask_continuation()` 通用续命架构（LLM 自评是否继续）、`ToolRegistry.execute()` 异常自愈（TypeError→结构化错误喂回 LLM）
- **CLI 大修**: `@app.callback` 直接启动、readline 历史/光标、termios 去 ^C 回显、Markdown 响应渲染、rule 分隔视觉区、退出钩子 `_on_exit`/`_run_exit_hooks`、Ctrl+C 两段式、`uv tool install -e .` 全局可用
- **Agent 增强**: `_ask_continuation()` 通用续命架构、工具错误自愈（registry try/except→喂回 LLM）、中间文字保留、`max_tool_calls` 走配置
- **压缩器重写**: Token 感知滑动窗口（`_sliding()`）、`_extend_to_chain()` 保证 tool_calls 链完整性、`max_input_tokens` 配置驱动（对标三家）
- **视觉打磨**: Panel 框回复（┌┐└┘）、`─── Agent ───` 统一分界、工具日志全回 stdout、无折叠逐条显示、Ctrl+C 取消补底线、Live spinner + timing
- **Skill 文档**: bugs.md +17 条修复，architecture.md +2 架构模式

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
| `agent.py` | 🟢 POLISHED | Full agent loop。工具调用：key=value + 终端宽度截断 + Live spinner/timing + `bright_black` 颜色 + 错误自愈（registry try/except）。超标时 `_ask_continuation()` 让 LLM 自评续命。中间文字 Panel 框。 |
| `config.py` | 🟢 REAL | Complete config system: `OpenMercuryConfig` + `ModelConfig` dataclass，JSON load/save，multi-path discovery，dict round-trip，merge()。Production-ready。|
| `llm.py` | 🟢 REAL | Full OpenAI-compatible async client：`chat()` (non-streaming, with tool calling) + `chat_stream()`。tool_calls JSON 解析正常。Production-ready。|
| `session.py` | 🟡 PARTIAL | `Session.add_message()` / `get_history()` 可用，但 `compact()` 为 `NotImplementedError`。`SessionStore.save()` / `.load()` / `.list_sessions()` 全部为 `NotImplementedError`。无持久化。|
| `message.py` | 🟢 REAL | `Message` dataclass + `to_dict()` + `MessageProcessor`。Production-ready。|
| `context.py` | 🟡 PARTIAL | `ContextManager.add()` / `needs_compression()` / `get_window()` 可用。但 `compress()` 为 `NotImplementedError`。`ContextCompressor.summarize()` / `extract_key_points()` 也是 `NotImplementedError`。Agent bypass 了 `context.compress()` 直接导入 `memory/compressor.py`。|

### openmercury/tools/ — Tool System

| File | Status | Details |
|------|--------|---------|
| `base.py` | 🟢 REAL | `BaseTool` ABC，`definition` property 生成 OpenAI function-calling schema，`validate()`。Production-ready。|
| `registry.py` | 🟢 REAL | `ToolRegistry`：register/unregister/get/list/get_definitions/async execute（含 try/except 异常转结构化错误）。Production-ready。 |
| `file_tools.py` | 🟢 REAL | `ReadFile` 支持 path/limit/offset（1-indexed），`WriteFile` 自动创建父目录。**未接入 Sandbox/权限检查。** |
| `bash_tools.py` | 🟢 REAL | `BashTool` 通过 `asyncio.create_subprocess_shell` 执行，支持 timeout + cwd，返回 stdout/stderr/returncode。**未调用 `SecurityChecker`，无沙箱隔离。** |
| `web_tools.py` | 🟡 PARTIAL | `WebFetch` 可用 (httpx + HTML strip)。`WebSearch` 为骨架 — 返回 `"not yet configured"`。|
| `task_tools.py` | 🔴 SKELETON | `TaskTool` 返回 `"not yet implemented"`，无子代理派发逻辑。|
| `mcp_tools.py` | 🔴 SKELETON | `MCPTool.execute()` 返回 `"not yet configured"`。`MCPManager.connect()`/`disconnect()` 为 `NotImplementedError`。|

### openmercury/skills/ — Skills System

| File | Status | Details |
|------|--------|---------|
| `loader.py` | 🟢 REAL | `SkillLoader`：递归扫描目录找 `SKILL.md`，解析 YAML frontmatter，返回结构化 dict。Production-ready。|
| `registry.py` | 🟢 REAL | `SkillRegistry`：register/unregister/get/list，keyword-based `get_relevant()`，`load_from_paths()` 对接 SkillLoader。Production-ready。|
| `builtin/` | 🔴 SKELETON | 空目录，无内置 skill。|

### openmercury/memory/ — Memory System

| File | Status | Details |
|------|--------|---------|
| `store.py` | 🟢 REAL | `MemoryStore`：JSON 文件 CRUD + tag 列表 + 文本匹配搜索。Production-ready。|
| `recall.py` | 🟢 REAL | `MemoryRecall`：关键词召回 + tag 筛选 + `get_relevant_context()`。Functional。|
| `compressor.py` | 🟢 REAL | `ContextCompressor` — token 感知滑动窗口（`_sliding()`）、锚点保留（system+第一条 user）、反序 token 预算填充、`_extend_to_chain()` 向前追溯补全 tool_calls 链。统计摘要。`max_input_tokens` 配置驱动。 |
| `search.py` | 🟢 REAL | `MemorySearch`：SQLite FTS5 全文索引。`index()` 写入，`search()` 查询。Production-ready。|

### openmercury/hooks/ — Hook System

| File | Status | Details |
|------|--------|---------|
| `registry.py` | 🟢 REAL | `HookRegistry`：on/off/emit/clear，检测 async/sync handler。Production-ready。|
| `lifecycle.py` | 🔴 SKELETON | 注册 4 个 hook 点 (`agent.start/stop`, `session.create/destroy`)，handler 均为 `pass`。|
| `chat_hooks.py` | 🔴 SKELETON | 注册 3 个 hook 点 (`message.receive/send`, `context.compact`)，handler 均为 `pass`。|
| `tool_hooks.py` | 🔴 SKELETON | 注册 3 个 hook 点 (`tool.before/after/error`)，handler 均为 `pass`。|

### openmercury/sandbox/ — Sandbox/Security

| File | Status | Details |
|------|--------|---------|
| `isolation.py` | 🟢 REAL | `SandboxIsolation`：临时目录创建/白名单/只读/穿越检测/清理。Full implementation。|
| `permissions.py` | 🟢 REAL | `PermissionManager`：allow/ask/deny 模式，fnmatch 规则，`check()`/`is_allowed()`/`needs_approval()`。Full implementation。|
| `security.py` | 🟢 REAL | `SecurityChecker`：正则危险命令检测 (rm -rf /, mkfs, dd, pipe-to-bash 等) + 路径穿越保护。Full implementation。|

### openmercury/scheduler/ — Scheduler

| File | Status | Details |
|------|--------|---------|
| `cron.py` | 🟢 REAL | `CronScheduler`：CronJob dataclass，add/remove/list，start 轮询 (60s)，stop。支持通配符和数字匹配。**异常处理静默吞错** (`pass # TODO`)。|
| `jobs.py` | 🟢 REAL | `TaskManager` + `Task` dataclass：create/get/update_status (含时间戳)，按状态 list。|
| `delivery.py` | 🟢 REAL | `DeliveryManager`：注册/投递渠道，含错误处理。**无预注册渠道**。|

### openmercury/observability/ — Observability

| File | Status | Details |
|------|--------|---------|
| `metrics.py` | 🟢 REAL | `MetricsCollector`：counter/timing/event/average/summary。Full implementation。|
| `audit.py` | 🟢 REAL | `AuditLogger`：JSON-lines 追加 + 限额读取。Full implementation。|
| `tracing.py` | 🟢 REAL | `TraceSpan` + `Tracer`：创建/结束/属性/耗时/ContextVar trace ID。Full implementation。|
| `logger.py` | 🟢 REAL | `setup_logger()`：Python logging，console + 可选 file。Production-ready。|

### openmercury/gateway/ — Message Gateways

| File | Status | Details |
|------|--------|---------|
| `base.py` | 🟢 REAL | `BaseGateway` ABC：`set_handler()`/`handle_message()`，抽象 `start()`/`stop()`/`send_message()`。Well-structured。|
| `telegram.py` | 🔴 SKELETON | 所有方法为 `pass` + `# TODO: 集成...`。无实际集成。|
| `discord.py` | 🔴 SKELETON | 同上。|

### cli/ — CLI Interface

| File | Status | Details |
|------|--------|---------|
| `main.py` | 🟢 POLISHED | `@app.callback` 无子命令启动。REPL：readline、termios ECHOCTL、Markdown 渲染、rule 视觉分隔、`_on_exit`/`_run_exit_hooks` 退出钩子、Ctrl+C 两段式。`uv tool install -e .` 全局可用。**仅注册 3 工具**。 |
| `tui.py` | 🔴 SKELETON | `run_tui()` 打印 `"TUI mode - coming soon"`。无 Textual/Rich 实现。|
| `commands.py` | 🔴 SKELETON | 仅注释 `# 命令将在 main.py 中统一定义`。|

### web/ — Web Interface

| File | Status | Details |
|------|--------|---------|
| `app.py` | 🟡 PARTIAL | FastAPI app：`/` (version)、`/health` (ok)、`/chat` (返回 `"coming soon"`)。**未对接 Agent**，无请求体模型，无会话管理。|

---

## Cross-Cutting Wiring Checks

| Integration | Verdict | Evidence |
|-------------|---------|----------|
| **Hooks → Agent** | ❌ NOT WIRED | `agent.py` zero imports from `openmercury/hooks`。No `HookRegistry` instantiated or `emit()`ed。Hooks 定义完整但无人调用。|
| **Sandbox → Tools** | ❌ NOT WIRED | `agent.py._execute_tool_calls()` 直接调 `tool_registry.execute()`，无权限/安全前缀。`bash_tools.py` 未 import `SecurityChecker`。`file_tools.py` 未使用 `SandboxIsolation`/`PermissionManager`。|
| **Observability → Agent** | ❌ NOT WIRED | `agent.py` zero imports from `openmercury/observability`。LLM 调用/Tool 执行时无 metrics 采集，无 tracing span，无 audit 记录。|
| **Memory → Sessions** | ❌ NOT WIRED | `agent.py.run()` 调 `session.add_message()` 但从不调 `MemoryStore.save()` 或 `MemoryRecall.recall()`。Context compressor 是 agent 自行导入的，未走 session 层。|
| **Scheduler → Runtime** | ❌ NOT RUNNING | `CronScheduler.start()` 需要 event loop。`cli/main.py` / `web/app.py` 均未实例化或启动 Scheduler。代码完整但从未激活。|
| **Skills → Agent** | ⚠️ PARTIAL | Agent 的 `_build_system_prompt()` 会注入 skill 内容到 system prompt (若 `skill_registry` 存在)。但 `cli/main.py` 从未创建 SkillRegistry 或加载 skills，所以 `skill_registry` 始终为 `None`。|

---

## 汇总

| Status | Count | 说明 |
|--------|-------|------|
| 🟢 REAL (可用) | 19 | 生产级或基本可用的独立模块 |
| 🟡 PARTIAL (部分) | 8 | 核心可用但有关键功能缺失 |
| 🔴 SKELETON (骨架) | 12 | 占位实现或空壳 |
| ❌ NOT WIRED (未集成) | 6 | 代码存在但调用链断开 — **最优先** |

## 下一步（按优先级）

1. **打通 Sandbox → Tools** — Bash/File 工具调用 SecurityChecker + SandboxIsolation
2. **打通 Hooks → Agent** — Agent Loop 关键节点 emit 事件
3. **打通 Observability → Agent** — LLM 调用/Tool 执行处埋点
4. **实现 Session 持久化** — SQLite 替换 `NotImplementedError`
5. **接入 LLM 上下文压缩** — 替换占位摘要为真实 LLM 调用
6. **实现 WebSearch** — 对接搜索 API
7. **实现 MCP 客户端协议**
8. **补充集成测试** — mock LLM 的 Agent-Loop 全覆盖测试
9. **打通 Memory → Sessions** — Agent 存储/召回会话记忆
10. **打通 Scheduler → Runtime** — CLI/Web 启动时激活
11. **通一个 Gateway** — Telegram 端到端
12. **TUI 实现** — Textual 替换 `"coming soon"`
