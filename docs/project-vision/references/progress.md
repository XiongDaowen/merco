# 项目进展

> 每次开发会话后更新。每次重大提交后必须根据提交内容同步更新。
> 最后更新: 2026-07-23 (波1 插件动态化完成)

## 目标对标

对标 **Hermes Agent** (自学习/记忆/多平台网关)、**OpenClaw** (多平台/插件/定时任务)、**OpenCode** (TUI/Skill/MCP)，取其三家之长，构建更精简、更可落地的 AI Agent 框架。

## 当前状态

**阶段**: Phase 5 完成 → v0.4.0 发布 | **焦点**: 插件动态化波1 完成（discovery + PluginSpec + manager 拓扑激活 + 两阶段 boot）

### 本次会话更新 (2026-07-23)

**插件动态化 波1（重大架构升级）**：
- **20 个 commit**（自 `3b07a88`：17 实现 + 1 polish `d99cc87` + 2 文档），最终代码 commit `d99cc87`。**910 passed / 1 skipped**。终审 **SHIP**。
- **目标**：可动态拓展--通过插件系统可动态安装插件进行拓展，架构清爽干净。
- **`plugins/discovery.py` (NEW, ~190 行)**：`PluginDiscovery` 无副作用发现器（仅吃 `config`，产出 `PluginSpec`）。两个来源：`entry_points(group="merco.plugins")`（从类属性读 priority/depends_on）+ `config.plugins_paths` 目录扫描（解析子目录 `plugin.toml`，`importlib.util.spec_from_file_location` 加载 `entry="module:Class"`，零 sys.path 污染，支持单文件插件）。目录扫描同名覆盖 entry_points；`enabled` 过滤；DFS 循环检测 + 存在性闭包剪枝。
- **`plugins/base.py`**：`Plugin` ABC 增 `priority: int = 50` + `depends_on: list[str] = []`。NEW `PluginSpec` dataclass（元数据 + 懒加载器 `load_cls()`/`instantiate()`，缓存 `_cls`/`_instance`）。`PluginContext` 增 `security_pipeline` 参数（**20** 注入属性，原 19）+ 4 便捷方法（`register_agent_profile`/`register_loop_policy`/`add_memory_backend`/`add_security_policy`，末者 `security_pipeline is None` 时抛 `RuntimeError`）。
- **`plugins/manager.py`**：`PluginManager` 增 `register_all(specs)` / `_resolve_order(names, boot_only)`（Kahn 拓扑排序，`(-priority, name)` tiebreak，存在性闭包，循环排除）/ `activate_boot()`（激活 `priority >= BOOT_PRIORITY=100`）/ `activate()` 懒实例化 + dep-active 检查（依赖未激活则跳过）/ `_emit_error()`（emit `plugin.error`）。`activate_all`/`activate_boot` 尊重 `config.plugins.<name>.enabled`。emit `plugin.activated`/`plugin.deactivated`/`plugin.error`。
- **`core/agent.py`**：装配段从 ~70 行硬编码 `from merco.plugins.builtin.*.plugin import *Plugin` + `register(*Plugin())` 重写为单行 `PluginDiscovery(config).discover()` + `register_all(...)`。`PluginContext(...)` 传入 `security_pipeline=self._security_pipeline`。`_initialize_async_plugins` 重写为**两阶段 boot**：`activate_boot()` → 绑定 `self.observer = ctx.observer` → `_restore_context()` → `activate_all()`。**零** `from merco.plugins.builtin.*` 导入残留。
- **`core/config.py`**：新增 `plugins_paths` 字段，默认 `["./.merco/plugins", "~/.config/merco/plugins"]`（镜像 `skills_paths`）。
- **`pyproject.toml`**：声明 7 个 `merco.plugins` entry_points。
- **7 个 builtin**（非 8）：observability(100)/skills(60)/mcp(50)/subagent(40)/web(30)/scheduler(20)/superpower(10)，全部经 entry_points 发现，priority 数据驱动 boot 序。修正旧文档虚构的 `PermissionPolicyPlugin`（不存在）。
- **分层**：`PluginDiscovery`（无副作用发现）→ `PluginSpec`（纯数据+懒加载）→ `PluginManager`（激活状态）→ `PluginContext`（被动扩展点袋）。7 个 builtin 现为"普通插件"，agent.py 零特殊分支。

### 本次会话更新 (2026-07-21)

**CLI UI 渲染快照测试体系（重大新增）**：
- **92 个新测试**，9 个测试文件：`test_dashboard.py` (16)、`test_prompt_area.py` (7)、`test_commands_ui.py` (22)、`test_lifecycle.py` (5)、`test_repl_errors.py` (13)、`test_cli_help.py` (3)、`test_main.py` (4)、`test_interrupt.py` (16)、`test_registry.py` (7)。全部 **94 pass**。
- **capture_console fixture**：基于 Rich `Console(record=True)` + 自定义 `_CaptureConsole.get_markup()` 双缓冲架构，同时捕获 ANSI 输出和原始 Rich markup 字符串。
- **make_fake_agent 工厂**：MagicMock agent，可控制 `run_return`/`run_side_effect`/`config_overrides`，统一测试 mock 基础设施。
- **Dashboard 区块覆盖率 100%**：WelcomeSection / ModelSection / ToolsSection / SkillsSection / ConfigSection / SessionSection / HintSection + Dashboard 组合渲染。
- **PromptArea 装饰器链测试**：空链 / 单 ContextBar / 多装饰器顺序 / 装饰器失败容错。
- **斜杠命令全量快照**：/help /model /context /tools /report /reload-mcp /mcp-status /sessions /exit /fork 等 22 条命令在多状态下的输出。

**CLI REPL 错误路径测试（核心）**：
- **`_run_one_turn()` 提取**：从 `run_repl()` 巨型 while 循环抽出独立测试单元，签名 `(agent, prompt_area, driver, handle_command, current_task_ref, console_obj=None) → str`。
- **13 个异常路径测试**：正常路径 / 流式抑制 Panel / 流式仍 Panel / 空响应 / RuntimeError / ConnectionError / TimeoutError / CancelledError / EOFError / KeyboardInterrupt / 斜杠命令。每条异常测试强制断言：`"Traceback" not in export_text` + `"File \"" not in export_text`。
- **LLM 调用失败 User Friendly 契约钉住**：`[red]错误: ...[/red]` 友好提示 + 零 traceback 泄漏。

**API 错误呈现重构（4 个 commit）**：
- **去 WARNING 泄漏**：`logger.warning(..., exc_info=True)` → `logger.info(...)`，非 debug 模式 WARNING 阈值抑制 INFO。traceback 保留在 `logger.debug(..., exc_info=True)`。
- **去 Panel 叠层**：`need_static = transient or (not buf)` 是错误的——每次 retry 多打一份 Panel。改为只在 except 块 `console.print(build_error_panel(...))`，每次 retry 一个完整 Panel。
- **流式模式 tool call 响应去重**：`_dispatch_tool_calls()` 在流式模式已通过 Live 显示内容后不再重复 `console.print(Panel(...))`。
- **错误响应渲染修正**：`Markdown(response)` 不渲染 Rich markup (`[bold red]`) → `Text.from_markup(response)`。

### 已完成的 Phase 3-5 项（上次更新后）

**Phase 3（MCP + Skill 完善）✅**：
- **MCP 客户端协议**：`merco/mcp/manager.py` + `tool.py` + `config.py` 完整实现。支持 `/mcp-status` / `/reload-mcp` CLI 命令。
- **Skill 系统**：`loader.py` + `registry.py` 完整。`builtin/` skills（merco、project-vision）已填充。

**Phase 4（CLI / Web 改进）✅**：
- **commands.py 从 🔴 SKELETON → 🟢 REAL**：27 个注册命令，6 个分组（info / session / search / memory / task / system / control）。`/fork` `/tree` `/history` `/search` `/recall` `/remember` `/memories` `/forget` `/plugins` `/todos` `/todo` `/todo-done` `/agents` `/agent` `/revert` 全部实现。
- **`_run_one_turn()` 提取**：REPL 主循环拆解，异常路径可独立测试。
- **InputInterrupt 管线**：CancelTaskStrategy / ClearInputStrategy / ExitWithHooksStrategy 三层策略链，支持双击退出 + 保存钩子。
- **Web 接口**：FastAPI app（`/` root、`/health`、`/chat`）仍 PARTIAL（未对接 Agent）。

**Phase 5（Memory + Session Fork）✅**：
- **Recaller 协议体系**：`BaseRecaller` ABC + `FTS5Recaller` + `MemoryRecaller` + `HybridRecaller` 全部实现。Agent 启动自动通过 `recaller.recall()` 注入上下文。
- **Session Fork + Tree**：`Session.fork()` + `SessionStore.clone_session()` + `get_children()` 完整实现。`/fork` `/tree` CLI 命令。
- **Memory Backend**：`MemoryBackend` ABC + `MemoryBackendRegistry`，支持 JSON backend。
- **Snapshot 文件追踪**：`merco/sandbox/snapshot.py` 10 个方法，支持 `/revert` 撤销文件修改。
- **Memory → Sessions 打通**：`/recall` 手动搜索 + `/search` FTS5 全文搜索 + auto recall。

**Phase 6（可观测性 + 错误处理）部分完成**：
- **`error_ui.py` (226 行)**：`classify_error()` 按 status_code + 异常类名 + 消息体分层分类（401/403/404/413/429/5xx/Timeout/Connection），`sanitize_message()` API key 脱敏，`build_error_panel()` Rich 红 Panel，`build_retry_line()` 重试行，`retry_spinner()` 异步 spinner。
- **Recovery Pipeline**：`WaitRecovery` 差异化退避（429/5xx→3s cap 30s；401/403/404→1s 仅一次；413→让 Compress 处理），`ModelFallbackRecovery` 备选模型切换。
- **LoopPolicy**：`loop_policy.py` (68 行)，决策动作（exit / continue / switch_model）。
- **压缩**：`CompressProcessor` 滑动窗口 + LLM 摘要。

**其他架构改进**：
- **Plugin 系统**：`PluginManager` + `PluginBase`，`builtin/` 目录含 ObservabilityPlugin / SkillPlugin / MCPPlugin / SubAgentPlugin / WebPlugin / SchedulerPlugin。
- **config.py 重大重构**：`ModelConfig.resolve()` 自动补齐 base_url/api_key，未注册 provider 只需显式写 base_url。
- **agent.py 膨胀到 1186 行**：集成 Stream/NonStream Provider 双模式、RecoveryPipeline、LoopPolicy、Hooks emit、ToolGuard、Observer、Session 持久化。是下一步重构目标。

---

## 里程碑

- [x] Phase 0: 项目初始化与 vision skill 创建
- [x] Phase 1: 核心 Agent-Loop 与基础工具
- [x] Phase 2a: 关键集成链路打通（Hooks/Sandbox/Observability）— v0.2.0
- [x] Phase 2b: Session 持久化 + Provider 架构 + setup 向导
- [x] Phase 3: Skill 系统完善 + MCP 集成 + API 错误可见性 — v0.3.0
- [x] Phase 4: 斜杠命令 + REPL 重构 + CLI UI 测试 + 错误呈现优化 — v0.4.0
- [x] Phase 5: Memory 召回体系 + Session Fork/Tree + Recaller 协议 + Snapshot 文件追踪
- [ ] Phase 6: 可观测性深化（tracing/metrics 可视化）+ 沙箱容器化 + LLM 摘要上下文压缩完善
- [ ] Phase 7: TUI + Web 对接 Agent + 多代理协作 + 文档/发布

---

## 模块逐项审计

### merco/core/ — Core Engine

| File | Status | Details |
|------|--------|---------|
| `agent.py` | 🟢 REAL | Full agent loop。Hooks 4 事件 emit、Observer 订阅、ToolGuard 拦截、SessionStore 持久化、`_wrap_up` 收尾、PromptBuilder+3 chunks、Pipeline (Result/Recovery/EmptyResponse) 完整集成、StreamingProvider/NonStreamingProvider 双模式、LoopPolicy 决策。1186 行。 |
| `config.py` | 🟢 REAL | `MercoConfig` + `ModelConfig` + `ProviderInfo` dataclass。5 个预置平台。`ProviderInfo.__getitem__` 向后兼容。`resolve()` 自动补 base_url/api_key。226 行。 |
| `setup.py` | 🟢 REAL | 交互式 API 配置向导，5 步流程。`merco setup` CLI 命令。192 行。 |
| `llm/` | 🟢 REAL | 模块化 LLM 层：`_client.py` (OpenAI 兼容客户端)、`errors.py` (向后兼容包装)、`error_ui.py` (226 行分类+渲染+重试反馈)。 |
| `session.py` | 🟢 REAL | Session 数据类 + save/load/resume_or_create + **`fork()` 已实现**。 |
| `context.py` | 🟢 REAL | `ContextManager` + `estimate_tokens`/`msg_tokens` + `total_tokens` 优先 API 实测。`CompressProcessor` 已实现（滑动窗口 + LLM 摘要）。 |
| `pipeline.py` | 🟢 REAL | `ResultPipeline` + `RecoveryPipeline` + `EmptyResponsePipeline`，链式 use()/process()。含 TruncationProcessor / SkillViewProcessor / WaitRecovery / ContextCompressRecovery / CallbackEmptyResponse。573 行。 |
| `loop_policy.py` | 🟢 REAL | LoopPolicy 决策（exit / continue / switch_model），68 行。 |
| `recovery/` | 🟢 REAL | `wait.py` (差异化退避) + `model_fallback.py` (备选模型切换)。 |

### merco/plugins/ — Plugin System

| File | Status | Details |
|------|--------|---------|
| `discovery.py` | 🟢 NEW | `PluginDiscovery` 无副作用发现器：entry_points(group="merco.plugins") + `plugins_paths` 目录扫描（plugin.toml manifest，`importlib.util.spec_from_file_location` 单文件加载，零 sys.path 污染）。同名目录覆盖 entry_points；enabled 过滤 + DFS 循环检测 + 存在性闭包剪枝。~190 行。 |
| `manager.py` | 🟢 REAL | PluginManager：`register_all(specs)` / `_resolve_order`(Kahn 拓扑 + `(-priority,name)` tiebreak) / `activate_boot`(priority>=100) / `activate` 懒实例化 + dep-active 检查 / `_emit_error`。emit `plugin.activated`/`deactivated`/`error`。 |
| `base.py` | 🟢 REAL | `Plugin` ABC(+`priority`/`depends_on`) + `PluginSpec` dataclass(懒加载 `load_cls`/`instantiate`) + `PluginContext`(20 注入属性 + 4 便捷方法 `register_agent_profile`/`register_loop_policy`/`add_memory_backend`/`add_security_policy`)。 |
| `builtin/` | 🟢 REAL | **7 个** builtin（observability/skills/mcp/subagent/web/scheduler/superpower）经 entry_points 发现，priority 标注 (100/60/50/40/30/20/10)。 |

### merco/mcp/ — MCP Integration

| File | Status | Details |
|------|--------|---------|
| `manager.py` | 🟢 REAL | MCPManager：load_config/reload/status/list_tools。 |
| `tool.py` | 🟢 REAL | MCP 工具包装 + 注册。 |
| `config.py` | 🟢 REAL | MCP 服务器配置。 |
| **集成** | ✅ WIRED | `/mcp-status` + `/reload-mcp` CLI 命令、agent.py 启动时 auto-load。 |

### merco/tools/ — Tool System

| File | Status | Details |
|------|--------|---------|
| `base.py` | 🟢 REAL | `BaseTool` ABC，`definition` property OpenAPI schema。 |
| `registry.py` | 🟢 REAL | `ToolRegistry`：register/unregister/execute（try/except 转结构化错误）。 |
| `file_tools.py` | 🟢 REAL | 流式行读 + head/tail + has_more。`write_file` 语义明确。 |
| `edit.py` | 🟢 REAL | SEARCH/REPLACE + diff 预览 + 确认。125 行。 |
| `bash_tools.py` | 🟢 REAL | `BashTool` asyncio subprocess。 |
| `skill_tools.py` | 🟢 REAL | `SkillViewTool` 动态描述。73 行。 |
| `web_tools.py` | 🟡 PARTIAL | `WebFetch` 可用。`WebSearch` 骨架。 |
| `task_tools.py` | 🟡 PARTIAL | 基础实现。Phase 7 多代理协作。 |
| `mcp_tools.py` | 🟢 REAL | MCP 工具发现 + 注册 ✅。 |

### merco/skills/ — Skills System

| File | Status | Details |
|------|--------|---------|
| `loader.py` | 🟢 REAL | 递归扫描 SKILL.md，YAML frontmatter。 |
| `registry.py` | 🟢 REAL | register/get/list/get_relevant/load_from_paths。 |
| `builtin/` | 🟢 REAL | merco + project-vision 内置 skill。 |

### merco/memory/ — Memory System

| File | Status | Details |
|------|--------|---------|
| `store.py` | 🟢 REAL | `MemoryStore`：JSON 文件 CRUD + tag + 文本匹配搜索。 |
| `recall.py` | 🟢 REAL | **Recaller 协议完整**：`BaseRecaller` ABC + `FTS5Recaller` + `MemoryRecaller` + `HybridRecaller`。Agent 自动 recall。 |
| `strategy.py` | 🟢 REAL | 召回策略。 |
| `backend.py` | 🟢 REAL | `MemoryBackend` ABC + `MemoryBackendRegistry`。 |
| `search.py` | 🟢 REAL | `MemorySearch`：SQLite FTS5 全文索引。 |
| `session_store.py` | 🟢 REAL | SQLite WAL 持久化。**`clone_session()`/`get_children()` 已实现** (Session Fork)。 |
| `session_search.py` | 🟢 REAL | 跨会话搜索。 |
| `save_pipeline.py` | 🟢 REAL | 记忆保存管线。 |

### merco/sandbox/ — Sandbox/Security

| File | Status | Details |
|------|--------|---------|
| `guard.py` | 🟢 REAL | `ToolGuard`：30 条默认 ask 规则链。166 行。 |
| `confirm.py` | 🟢 REAL | edit_file 确认交互。 |
| `isolation.py` | 🟢 REAL | `SandboxIsolation`：临时目录创建/白名单/只读/穿越检测/清理。 |
| `permissions.py` | 🟢 REAL | `PermissionManager`：allow/ask/deny 模式。 |
| `security.py` | 🟢 REAL | `SecurityChecker`：正则危险命令检测。 |
| `snapshot.py` | 🟢 REAL | 文件快照追踪（10 个方法），支持 `/revert`。 |

### merco/observability/ — Observability

| File | Status | Details |
|------|--------|---------|
| `observer.py` | 🟢 REAL | Observer 门面：hooks 订阅 + 双计数器 (live+acc_map)。139 行。 |
| `metrics.py` | 🟢 REAL | `MetricsCollector`：counter/timing/event/average/summary。 |
| `audit.py` | 🟢 REAL | `AuditLogger`：JSON-lines 追加 + 限额读取。 |
| `tracing.py` | 🟢 REAL | `TraceSpan` + `Tracer`。 |
| `logger.py` | 🟢 REAL | `setup_logger()`。 |

### cli/ — CLI Interface

| File | Status | Details |
|------|--------|---------|
| `main.py` | 🟢 REAL | Typer CLI：`run` (REPL，`_run_one_turn()` 提取)、`init`、`skills`、`setup`。Dashboard 可组合架构 + PromptArea 装饰器链。异常路径 User Friendly（`[red]错误: ...[/red]` + 零 traceback）。597 行。 |
| `commands.py` | 🟢 REAL | **27 个注册命令**（从 🔴 SKELETON 升级）。6 个分组：info（help/model/context/tools/report/reload-mcp/mcp-status）、session（new/sessions/fork/tree/history/revert）、search（search/recall）、memory（remember/memories/forget）、task（todos/todo/todo-done/agents/agent）、system（plugins）+ control（exit/quit/q）。518 行。 |
| `registry.py` | 🟢 REAL | CommandRegistry + CommandDef，register/get/match/get_all/get_help_text。 |
| `input_driver.py` | 🟢 REAL | PromptToolkitInput + InputInterrupt。 |
| `interrupt.py` | 🟢 REAL | InterruptPipeline：CancelTaskStrategy / ClearInputStrategy / ExitWithHooksStrategy 三层策略。 |
| `tui.py` | 🔴 SKELETON | `"TUI mode - coming soon"`。Phase 7。 |

### web/ — Web Interface

| File | Status | Details |
|------|--------|---------|
| `app.py` | 🟡 PARTIAL | FastAPI app：`/` (version)、`/health` (ok)、`/chat` (`"coming soon"`)。未对接 Agent。 |

### tests/cli/ — CLI 测试（新增）

| File | Status | Details |
|------|--------|---------|
| `conftest.py` | 🟢 REAL | `capture_console` fixture + `make_fake_agent` 工厂 + `_CaptureConsole` 双缓冲 Console 子类。 |
| `test_dashboard.py` | 🟢 REAL | 16 个测试：6 个 DashboardSection 区块 + Dashboard 组合渲染 + 容错。 |
| `test_prompt_area.py` | 🟢 REAL | 7 个测试：PromptArea 装饰器链 + ContextBar + 去重。 |
| `test_commands_ui.py` | 🟢 REAL | 22 个测试：全部 6 个分组斜杠命令输出快照。 |
| `test_lifecycle.py` | 🟢 REAL | 5 个测试：启动 banner / 调试模式 / 配置错误 / init。 |
| `test_repl_errors.py` | 🟢 REAL | 13 个测试：`_run_one_turn()` 异常路径全覆盖（核心）。 |
| `test_main.py` | 🟢 REAL | `_fmt` 格式化 + 兼容性测试。 |
| `test_interrupt.py` | 🟢 REAL | 16 个测试：InterruptPipeline 策略链 + sync/async 双路径。 |
| `test_registry.py` | 🟢 REAL | 7 个测试：CommandRegistry + 单例隔离。 |

---

## Cross-Cutting Wiring Checks

| Integration | Verdict | Details |
|-------------|---------|---------|
| **Hooks → Agent** | ✅ WIRED | `agent.py` 实例化 `HookRegistry`+`Observer`，4 事件 emit。Observer 订阅计数。 |
| **Sandbox → Tools** | ✅ WIRED | `agent.py` 实例化 `ToolGuard`，`_execute_tool_calls` 前 `await self.guard.check()`。 |
| **Observability → Agent** | ✅ WIRED | Observer 双计数器。`/report` 命令显示统计。重启从 SQLite 恢复 acc。 |
| **SessionStore → Agent** | ✅ WIRED | `Session.resume_or_create` 自动恢复，每轮 `session.save()`。 |
| **MCP → Agent** | ✅ WIRED | `/mcp-status` + `/reload-mcp` CLI、agent.py 启动自动 load_config。 |
| **Memory → Sessions** | ✅ WIRED | Agent 自动 recall + `/recall` 手动搜索 + `/search` FTS5。 |
| **Recaller → Agent** | ✅ WIRED | `BaseRecaller` → `FTS5Recaller` → `MemoryRecaller` → `HybridRecaller` 四级协议。Agent 启动自动注入。 |
| **Session Fork → Agent** | ✅ WIRED | `Session.fork()` + `/fork` + `/tree` CLI 命令 + `snapshot.set_current_session()`。 |
| **Snapshot → Agent** | ✅ WIRED | 文件快照追踪，`/revert` 撤销修改。 |
| **Plugins → Agent** | ✅ WIRED | discovery 驱动装配：`PluginDiscovery(config).discover()` + `register_all`，两阶段 boot（`activate_boot` → restore → `activate_all`）。7 个 builtin 经 entry_points。`/plugins` CLI。 |
| **Scheduler → Runtime** | ❌ NOT WIRED | CLI/Web 未启动 CronScheduler。代码完整但从未激活。Phase 6。 |
| **TUI** | ❌ NOT WIRED | `tui.py` 仍为占位。Phase 7。 |
| **Web → Agent** | ❌ NOT WIRED | `/chat` 返回 `"coming soon"`。Phase 7。 |
| **SubAgent** | ❌ NOT WIRED | `task_tools.py` 基础实现，多代理协作未完全打通。Phase 7。 |
| **Gateway** | ❌ NOT WIRED | Telegram/Discord gateway 仅骨架。Phase 7。 |

---

## 汇总

| Status | Count | 说明 |
|--------|-------|------|
| 🟢 REAL (可用) | 35 | 生产级或基本可用的独立模块（+1：新增 `plugins/discovery.py`） |
| 🟡 PARTIAL (部分) | 3 | web/app.py / web_tools / task_tools |
| 🔴 SKELETON (骨架) | 2 | tui.py / 2 个 gateway |
| ❌ NOT WIRED (未集成) | 4 | Scheduler → Runtime / TUI / Web → Agent / SubAgent |
| **CLI 测试** | **94** | 9 个测试文件，覆盖 Dashboard / PromptArea / commands / lifecycle / REPL errors |
| **Plugin 测试** | **新增** | test_discovery / test_spec / test_manager / test_plugin_base / test_plugin_integration + 7 个 builtin 插件测试 |
| **总测试** | **910 passed / 1 skipped** | 波1 插件动态化后全量 |

## 下一步（按优先级）

### Phase 6（可观测性深化 + 沙箱容器化）
1. **Scheduler 接入 CLI** — `run_repl` 启动 CronScheduler
2. **LLM 摘要上下文压缩** — `CompressProcessor._summarize` 对接真实 LLM
3. **Docker 沙箱** — 替换临时目录

### Phase 7（界面 + 多代理 + 发布）
4. **TUI 实现** — Textual 替换 `"coming soon"`
5. **Web 对接 Agent** — `app.py` 接入 Agent + 会话管理
6. **SubAgent 多代理协作** — `task_tools.py` 完整实现
7. **Gateway 实现** — Telegram/Discord

### 插件动态化（波2/波3）
- **波1 ✅ 完成**（2026-07-23）：discovery + PluginSpec + manager 拓扑激活 + 两阶段 boot。
- **波2** - ModelProviderRegistry：动态模型供应商，镜像插件发现机制。
- **波3** - Scheduler->Runtime + GatewayRegistry：调度器升级为 Runtime + 网关动态注册。

### 持续
- **agent.py 拆分** — 1186 行太重，StreamingProvider / NonStreamingProvider 可独立文件
- **补充端到端测试** — 真实 LLM 的集成测试
- **PyPI 发布** — 发布 v0.4.0 并写 changelog
