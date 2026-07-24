# 项目进展

> 每次开发会话后更新。每次重大提交后必须根据提交内容同步更新。
> 最后更新: 2026-07-24 (Wave 3 完成 + 去债 ruff 498→0 + pre-commit + 测试跳过修复 → 999 passed / 0 skipped / 0 failed)

## 目标对标

对标 **Hermes Agent** (自学习/记忆/多平台网关)、**OpenClaw** (多平台/插件/定时任务)、**OpenCode** (TUI/Skill/MCP)，取其三家之长，构建更精简、更可落地的 AI Agent 框架。merco 的差异化路径：插件全动态化（discovery → spec → manager → context → 8 个 builtin）、模型供应商动态化（ABC → registry → 双 provider）、gateway/runtime 薄宿主 + 失败隔离、单事件循环 CLI 收尾、代码零技术债（ruff=0 + pre-commit 防回归）、prompt-level 自进化储备（见 `next-focus.md`）。

## 当前状态

**阶段**: Wave 1+2+3 插件/模型/gateway 动态化 完成 + 技术债清零（ruff 498→0 + pre-commit）| **焦点**: 下一站候选方向——`Self-Improving Agent Loop`（见 `references/next-focus.md`）

### 本次会话更新 (2026-07-24) - Wave 3 Scheduler→Runtime + GatewayRegistry

**插件动态化 波3（重大架构升级）**：
- **12 个 commit**（自 `97e70fc`：5 重构/gateway 基础 + 3 scheduler/agent 接线 + 2 CLI 单 loop + 2 测试/spec 文档），分支 `wave3/runtime-gateway-registry` 推上 main 落点 `d92d958`。**998 passed / 1 skipped**（1 skip = `test_execute_command_with_non_utf8_output`，见本次会话第 3 节）。
- **目标**：把 Scheduler 从"代码完整但从未激活"升级为运行时基础设施，新增 Gateway 动态注册机制——薄宿主 AgentRuntime 统一调度 Agent + CronScheduler + GatewayRegistry，让 CLI/Web/gateway/Cron 都能复用同一套生命周期。
- **`merco/core/runtime.py` (NEW, ~117 行)**：`AgentRuntime` 生命周期宿主。owns Agent + CronScheduler + GatewayRegistry；`start()` 幂等（必要时 `Agent.create()` 触发插件两阶段激活）→ 绑 `inbound handler` → `gateway_registry.start_all()` → `scheduler.start()` 后台 task；`stop()` 幂等（gateway → scheduler → scheduler task 取消，partial-start 也能清理）；`submit(prompt)` 给 cron job；`handle_inbound(source, chat_id, message)` 给 gateway inbound（chat_id 保留前向兼容，**Wave 3 单 session 不做 per-chat_id 隔离**，见 spec §6）。`agent` property：start() 前访问抛 RuntimeError。
- **`merco/gateway/base.py` (NEW)**：`GatewayAdapter` ABC（`name` 类属性 + `start/stop/send_message` abstract + `set_message_handler(handler)`）。Inbound 协议 = `handler(chat_id, message) -> reply`（async）。
- **`merco/gateway/registry.py` (NEW, ~74 行)**：`GatewayRegistry` 注册表 + 生命周期管理。`register/get/list`（重复名 raise，对齐 ModelRegistry 严格语义） + `set_inbound_handler(handler)` + `start_all()`（逐 adapter 绑定 `_bound(name)` closure → start，单个失败隔离）+ `stop_all()`（逐 adapter stop，partial-start 也能容忍）。**闭包 bug 防护**：`_bound(chat_id, message, _name=name)` 用默认参捕获本轮 name，避免循环晚绑定到最后一个 adapter（registry.py:57）。
- **`merco/gateway/webhook.py` (NEW, ~80 行)**：`WebhookGateway` 参考适配器，FastAPI/uvicorn 实现，`port=0` 让 OS 分配空闲端口，启动后 `actual_port` 可读；POST `/message` → 调用 `message_handler(chat_id, body)` → JSON `{reply: ...}`。
- **`merco/plugins/builtin/gateway/plugin.py` (NEW, 8th builtin, priority=25)**：`GatewayPlugin` 注册内置 `WebhookGateway`，走 PluginContext 注入 `gateway_registry`。
- **`merco/plugins/base.py`**：`PluginContext` 注入属性从 22 → **23**（`gateway_registry`）+ 便捷方法从 10 → **11**（`register_gateway(adapter)`）。
- **`merco/core/agent.py`**：构造期接入 `gateway_registry`（`plugin_ctx` property + 装配到 `ctx.gateway_registry`，让 `Runtime.start()` 能拿到）。
- **CLI 单事件循环重构**：`_setup_agent()` 改 sync，构造 `AgentRuntime(config=cfg, tool_registry=tool_registry)` 返回 **未启动** Runtime（cli/main.py:154-310）；`repl()` 内 `await runtime.start()` + `agent = runtime.agent`（cli/main.py:502-503），`finally` 块 `await runtime.stop()`（cli/main.py:568-569）。**全文件仅一处 `asyncio.run(repl())`**（cli/main.py:571），消除之前 `_setup_agent` 内部 asyncio.run + CLI 顶层再 run 的双 loop。
- **删除死代码**（Wave 3 内部 + T1 合并）：
  - `merco/scheduler/delivery.py`（DeliveryManager 占位）、`merco/scheduler/jobs.py`（TaskManager 占位）、`merco/gateway/telegram.py`、`merco/gateway/discord.py`（commit `97e70fc`，4 文件 -144 行）
  - `merco/tools/mcp_tools.py`（commit `ab20c07`，MCP 已由 `merco/mcp/` 实现）
- **架构分层**：`GatewayAdapter`（契约 ABC）→ `GatewayRegistry`（注册表 + 生命周期 + 失败隔离）→ 具体 adapter（如 `WebhookGateway`）→ `AgentRuntime` 统一宿主 → CLI/Web/cron 经 `submit`/`handle_inbound` → `agent.run`。镜像插件 / 模型层的分层（ABC → registry → 实现 → consumer）。
- **设计文档**：`docs/superpowers/specs/2026-07-23-scheduler-runtime-gateway-registry-design.md` + `docs/superpowers/plans/2026-07-23-scheduler-runtime-gateway-registry.md`（spec §6 单 session / §7 ctx accessor / §9 CLI 单 loop / §11 FastAPI 事实修正全部采纳）。

### 本次会话更新 (2026-07-24) - 去债浪潮（ruff 498→0 + pre-commit）

**技术债清零（系统性清理）**：
- **8 个 commit**（`ab20c07`..`50c511a` + `d92d958`），分支 `debt-cleanup` 推上 main 落点 `d92d958`。**8 个任务 T1-T8**，子 agent 驱动 + 右尺寸评审。
- **T1 死代码 stub 删除**（commit `ab20c07`）：`cli/tui.py`（Phase 7 TUI 占位）+ `merco/tools/mcp_tools.py`（MCP 已由 `merco/mcp/` 实现）。`merco/tools/__init__.py` 移除 mcp_tools re-export。3 文件 -66 行。
- **T2 真实类型洞修复**（commit `dafa879`）：4 个 F821（`TYPE_CHECKING` 缺漏：`Agent` 在 `merco/core/llm/response.py`、`ModelConfig` 在 `merco/core/pipeline.py`）；1 个 F811（response.py import shadowing——移除冗余本地 `_json`/`Live`/`Group`，保留 `console` local 用于避开循环）；3 个 F841（未用局部变量，保留 side-effects）。
- **T3 F401 未用 import 大扫除**（commit `3b495d9`）：86 → 0。先识别 side-effect imports：`cli.commands` 加 `# noqa: F401`（命令注册触发）、sandbox `_DEFAULT_RULES` 加进 `__all__`、`SkillLoader` 整个删除（确为 dead）。autofix 后**意外发现并修复 52 个集成测试断**：conftest `_isolation_services` fixture 被 autofix 当未用删掉——手动 re-export + noqa 恢复。
- **T4 ruff autofix 简单项**（commit `4b4facd`）：I001 (203→0 import 排序) + W292 (16→0 尾换行) + F541 (12→0 空 f-string)。
- **T5 pyupgrade**（commit `83f9b7c`）：UP037 (59→0 去注解引号) + UP035 (11→0 `typing.List` → `list`)。**关键判断**：仓库已对所有带 quoted annotation 的文件加 `from __future__ import annotations`，所以 safe-fix（仅改 import / 不动运行时行为）覆盖全部；仓库确认 **未使用 Pydantic / `get_type_hints`**，无运行时风险。
- **T6 ruff format 全仓**（commit `50c511a` 上半）：`ruff format .` 191 个文件纯格式化（+2308 / -1488 行）；big-bang。
- **T7 手动残余清理**（commit `2dfa556`）：N818 (10 noqa'd——保留 `InputInterrupt` / `GuardConfirmationRequired` 业务命名) + N806 (6 重命名局部变量) + F841 (5 修) + E501 (2 rewrap) + F811 (2 修：`isolation_services` fixture 移到 `tests/integration/conftest.py` + 删空 `tests/integration/core/isolation.py`) + E731 (1 lambda → def) + UP042 (`MessageRole str, Enum` → `StrEnum`，行为安全验证)。
- **T8 pre-commit 钩子**（commit `d92d958`）：新增 `.pre-commit-config.yaml`，本地 `uv run ruff` hooks（与项目 venv 版本对齐，防版本漂移）。**ruff 配置 0 改动**（`pyproject.toml` `[tool.ruff]` / `[tool.ruff.lint]` 完全不变——零规则禁用，纯靠修复达成 0 error）。
- **结果**：`ruff check .` **498 → 0**，`ruff format --check .` **0**，`pytest` **998/1/0**，pre-commit 强制门。

### 本次会话更新 (2026-07-24) - 测试跳过修复

**测试跳过修复（真 bug，不是 stale debt）**：
- **1 commit**（`e7dd024`），分支 `fix/bash-non-utf8-test` 推上 main。`pytest` **998/1/0 → 999/0/0**。
- **根因**：`tests/tools/test_bash_tools.py::test_execute_command_with_non_utf8_output` 用 `printf '\xff\xfe\xfd'` 生成二进制输出，但仓库默认 `/bin/sh` 是 **dash**，dash `printf` **不支持 `\x` hex escape**——输出变成了字面字符串 `\xff\xfe\xfd`（含反斜杠与字母），断言 `assert "�" in stdout` **不可能通过**（输出里没有 `�`，也没法产生）。
- **修复**：测试重写为 `cat` 一个真实二进制文件（`b"\xff\xfe\xfd"` 由 Python `tmp_path / "bin"` 写入）。避开 shell escape 陷阱，直接验证 `decode(errors="replace")` 从 invalid UTF-8 字节产生 `�` 替换字符。
- **结论**：跳过不是 stale debt 是真 bug；shell 兼容性问题（dash vs bash）原本靠 `pytest.skip` 掩盖，实质是测试方法不可靠。修复后 999 全绿。

### 本次会话更新 (2026-07-23) - 波2 ModelProviderRegistry

**模型供应商动态化 波2（重大架构升级）**：
- **18 个 commit**（自 `95e300d9`：1 spec 文档 + 16 实现/重构/测试 + 1 no-debt gate `4951099`），最终代码 commit `4951099`。**945 passed / 1 skipped**。终审 **SHIP**。
- **目标**：模型供应商动态化--镜像插件发现机制，第三方可通过 `PluginContext.model_registry` 注册自有 provider，agent 不再硬编码 OpenAI 客户端。ABC 不被 OpenAI 形状绑架（`AnthropicNativeProvider` 原生 Messages API 证明）。
- **`llm/base.py` (NEW)**：`ModelProvider` ABC（`chat`/`chat_stream`/`info`）+ `ModelProviderInfo` dataclass（name/provider_class/display_name/base_url/key_env/key_help/default_model/models/description）。
- **`llm/registry.py` (NEW)**：`ModelRegistry` 单一真相源--`register/get/list/select`。`select()` 拥有凭证解析（读 `key_env` -> env -> config -> `ModelConfig.api_key`），agent/config 不再各自补 base_url/api_key。`_BUILTIN_PROVIDERS` 预置 OpenAICompatible/AnthropicNative。
- **`llm/openai_provider.py` (NEW)**：`OpenAICompatibleProvider` 吸收旧 `LLMClient` transport（`AsyncOpenAI` 构造 + chat/chat_stream + tool_calls 解析 + None 字段防护），拥有 `translate_openai_error`（SDK 异常 -> ProviderError）。
- **`llm/anthropic_provider.py` (NEW)**：`AnthropicNativeProvider` 原生 Messages API（非 OpenAI 兼容 shim），证明 ABC 不被 OpenAI 形状绑架；拥有 `translate_anthropic_error`。新增 `anthropic` 依赖。
- **`llm/thinking.py` (NEW, 纯提取)**：`ThinkingExtractor` 策略链（从 `_client.py` 原样搬出）。
- **`llm/response.py` (NEW, 纯提取)**：`ResponseProvider`/`StreamingProvider`/`NonStreamingProvider`（从 `agent.py` 原样搬出）。
- **`llm/errors.py`**：SDK 无关的 `ProviderError` 层级（`RateLimitError`/`AuthError`/`ConnectionError`/`ModelNotFoundError`，携带 `status_code`）。`translate_*_error` 移入各 provider 文件（errors.py 不再 import 任何 SDK）。保留 `llm_error` 兼容包装；删除死 re-export `build_error_panel` + `# noqa: F401`。
- **`core/config.py`**：`ModelConfig` 纯数据（删 `resolve()`/`stream_options`，凭证交给 `ModelRegistry.select()`）；新增 `StreamingConfig` 分组（enabled/think/content/think_transient/render_interval）。
- **`core/agent.py`**：`provider` 懒属性（首次访问 `ModelRegistry.select(config.model)`，setter 走 `switch_model`）+ `model_registry` 字段。`switch_model` 跨 provider 修复（构造新 `ModelConfig` 触发 re-select，而非假设同 client）。`_model_provider`/`_response_provider` 内部槽。删 `agent.llm` 别名 + `LLMClient` 构造 + `_get_api_key`。
- **`plugins/base.py`**：`PluginContext` 增 `model_registry` 注入 + `register_model_provider()` 便捷方法（第三方扩展点）。memory strategy 用 deferred provider getter。
- **删除**：`_client.py`、`PROVIDER_REGISTRY`、`ProviderInfo`、`resolve()`、`_get_api_key`、`LLMClient`/`MockLLMClient`/`ProgrammableLLMClient` 及全部迁移别名。4-grep no-debt gate 全空。
- **分层**：`ModelProvider` ABC（契约）-> `ModelProviderInfo`（纯元数据）-> `ModelRegistry`（单一真相源 + 凭证解析）-> 具体 provider（各自拥有 SDK error mapping）-> `agent.provider` 懒属性。镜像插件分层（discovery -> spec -> manager -> context）。

### 本次会话更新 (2026-07-23) - 波1 插件动态化

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
- **Plugin 系统**（**Wave 1+2+3 完成**）：`PluginManager` + `PluginBase` + `PluginDiscovery` + `PluginSpec` + `PluginContext` (23 注入属性 + 11 便捷方法)；8 个 builtin 经 entry_points 发现（observability/skills/mcp/subagent/web/scheduler/superpower/**gateway**），priority 数据驱动 boot 序（100/60/50/40/30/25/20/10）。
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
- [x] **插件动态化 波1** (2026-07-23, `d99cc87`)：discovery + PluginSpec + manager 拓扑激活 + 两阶段 boot
- [x] **插件动态化 波2** (2026-07-23, `4951099`)：ModelProvider ABC + ModelRegistry 单一真相源 + OpenAI/Anthropic 双 provider
- [x] **插件动态化 波3** (2026-07-24, `d92d958`)：AgentRuntime 生命周期宿主 + GatewayRegistry + WebhookGateway + CLI 单事件循环
- [x] **技术债清零** (2026-07-24, `d92d958`)：ruff 498→0 + pre-commit 防回归（零规则禁用，纯修复达成）
- [x] **测试跳过修复** (2026-07-24, `e7dd024`)：dash shell `\x` escape 不兼容真 bug，cat 二进制文件替 printf，999/0/0
- [ ] Phase 6: 可观测性深化（tracing/metrics 可视化）+ 沙箱容器化 + LLM 摘要上下文压缩完善
- [ ] Phase 7: TUI + Web 对接 Agent + 多代理协作 + 文档/发布

---

## 模块逐项审计

### merco/core/ — Core Engine

| File | Status | Details |
|------|--------|---------|
| `agent.py` | 🟢 REAL | Full agent loop。Hooks 4 事件 emit、Observer 订阅、ToolGuard 拦截、SessionStore 持久化、`_wrap_up` 收尾、PromptBuilder+3 chunks、Pipeline (Result/Recovery/EmptyResponse) 完整集成、StreamingProvider/NonStreamingProvider 双模式、LoopPolicy 决策。1186 行。 |
| `config.py` | 🟢 REAL | `MercoConfig`（主配置，load/save/merge + JSON 序列化）+ `ModelConfig`（纯数据袋，`resolve()`/`stream_options` 已删，凭证交 `ModelRegistry.select()`）+ `StreamingConfig` 分组（enabled/think/content/think_transient/render_interval）。`ProviderInfo`/`PROVIDER_REGISTRY` 已删（波2）。259 行。 |
| `setup.py` | 🟢 REAL | 交互式 API 配置向导，5 步流程。`merco setup` CLI 命令。192 行。 |
| `llm/` | 🟢 REAL | 模块化 LLM 层（波2 重构）：`base.py` (ModelProvider ABC + ModelProviderInfo)、`registry.py` (ModelRegistry 单一真相源)、`openai_provider.py`/`anthropic_provider.py` (双 provider，各自拥有 SDK error mapping)、`thinking.py`/`response.py` (提取)、`errors.py` (SDK 无关 ProviderError 层级)、`error_ui.py` (分类+渲染+重试反馈)。 |
| `session.py` | 🟢 REAL | Session 数据类 + save/load/resume_or_create + **`fork()` 已实现**。 |
| `context.py` | 🟢 REAL | `ContextManager` + `estimate_tokens`/`msg_tokens` + `total_tokens` 优先 API 实测。`CompressProcessor` 已实现（滑动窗口 + LLM 摘要）。 |
| `pipeline.py` | 🟢 REAL | `ResultPipeline` + `RecoveryPipeline` + `EmptyResponsePipeline`，链式 use()/process()。含 TruncationProcessor / SkillViewProcessor / WaitRecovery / ContextCompressRecovery / CallbackEmptyResponse。573 行。 |
| `loop_policy.py` | 🟢 REAL | LoopPolicy 决策（exit / continue / switch_model），68 行。 |
| `recovery/` | 🟢 REAL | `wait.py` (差异化退避) + `model_fallback.py` (备选模型切换)。 |
| `runtime.py` | 🟢 NEW | **Wave 3**：`AgentRuntime` 生命周期宿主（~117 行）。owns Agent + CronScheduler + GatewayRegistry；`start()/stop()` 幂等；`submit(prompt)` 给 cron job；`handle_inbound(source, chat_id, message)` 给 gateway inbound（单 session，chat_id 仅前向兼容）。 |

### merco/plugins/ — Plugin System

| File | Status | Details |
|------|--------|---------|
| `discovery.py` | 🟢 NEW | `PluginDiscovery` 无副作用发现器：entry_points(group="merco.plugins") + `plugins_paths` 目录扫描（plugin.toml manifest，`importlib.util.spec_from_file_location` 单文件加载，零 sys.path 污染）。同名目录覆盖 entry_points；enabled 过滤 + DFS 循环检测 + 存在性闭包剪枝。~190 行。 |
| `manager.py` | 🟢 REAL | PluginManager：`register_all(specs)` / `_resolve_order`(Kahn 拓扑 + `(-priority,name)` tiebreak) / `activate_boot`(priority>=100) / `activate` 懒实例化 + dep-active 检查 / `_emit_error`。emit `plugin.activated`/`deactivated`/`error`。 |
| `base.py` | 🟢 REAL | `Plugin` ABC(+`priority`/`depends_on`) + `PluginSpec` dataclass(懒加载 `load_cls`/`instantiate`) + `PluginContext`(**23** 注入属性 + **11** 便捷方法 `register_agent_profile`/`register_loop_policy`/`add_memory_backend`/`add_security_policy`/`register_model_provider`/`register_gateway`)。Wave 3 加 `gateway_registry` + `register_gateway`。 |
| `builtin/` | 🟢 REAL | **8 个** builtin（observability/skills/mcp/subagent/web/scheduler/superpower/**gateway**）经 entry_points 发现，priority 标注 (100/60/50/40/30/20/10/**25**)。Wave 3 新增 GatewayPlugin（priority=25）。 |

### merco/mcp/ — MCP Integration

| File | Status | Details |
|------|--------|---------|
| `manager.py` | 🟢 REAL | MCPManager / MCPServerManager：load_config/reload/status/list_tools。 |
| `tool.py` | 🟢 REAL | MCP 工具包装 + 注册。 |
| `config.py` | 🟢 REAL | MCP 服务器配置。 |
| **集成** | ✅ WIRED | `/mcp-status` + `/reload-mcp` CLI 命令、agent.py 启动时 auto-load。 |
| **dead stub** | ❌ 已删 | `merco/tools/mcp_tools.py`（Wave 3 T1 `ab20c07` 删）——MCP 真实实现均在 `merco/mcp/`，stub 仅为旧版占位。 |

### merco/gateway/ — Gateway Subsystem（Wave 3 新增）

| File | Status | Details |
|------|--------|---------|
| `base.py` | 🟢 NEW | `GatewayAdapter` ABC：`name` 类属性 + abstract `start/stop/send_message` + `set_message_handler(handler)`；inbound 协议 = `handler(chat_id, message) -> reply` (async)。 |
| `registry.py` | 🟢 NEW | `GatewayRegistry`（~74 行）：`register/get/list` + `set_inbound_handler` + `start_all`/`stop_all`（逐 adapter 失败隔离）。`_bound(name)` 用默认参捕获本轮名避免循环晚绑定 bug（registry.py:57）。 |
| `webhook.py` | 🟢 NEW | `WebhookGateway` 参考适配器（~80 行）：FastAPI/uvicorn，`port=0` OS 分配端口，启动后 `actual_port` 可读；POST `/message` → JSON `{reply: ...}`。 |
| `telegram.py` / `discord.py` | ❌ 已删 | Wave 3 准备期 `97e70fc` 删——仅为旧版占位，无实现。 |
| **集成** | ✅ WIRED | `GatewayPlugin` (priority=25) 经 entry_points 注册 `WebhookGateway`；`PluginContext.gateway_registry` + `register_gateway()` 注入；`AgentRuntime.start()` 调 `gateway_registry.start_all()`，`handle_inbound()` 路由到 `agent.run`。 |

### merco/scheduler/ — Cron Scheduler（Wave 3 接通）

| File | Status | Details |
|------|--------|---------|
| `cron.py` | 🟢 REAL | `CronScheduler` 阻塞 while 循环——Wave 3 commit `d8b1ff6` 修复异常不吞 / weekday Sun=0 / 诚实 docstring；`SchedulerPlugin` (priority=20) 经 entry_points 注册注入 ctx。 |
| `delivery.py` / `jobs.py` | ❌ 已删 | Wave 3 准备期 `97e70fc` 删——DeliveryManager / TaskManager 占位无实现。 |
| **集成** | ✅ WIRED | Wave 3 `AgentRuntime.start()` 后台 task 跑 `scheduler.start()`，`stop()` 收尾；`runtime.submit(prompt)` 给 cron job 入口。 |

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
| `mcp_tools.py` | ❌ 已删 | T1 (`ab20c07`) 删除——MCP 由 `merco/mcp/` 真实实现，stub 仅为旧版占位。 |

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
| `tui.py` | ❌ 已删 | T1 (`ab20c07`) 删除——原为 `"TUI mode - coming soon"` 占位；Phase 7 真实现时直接用 textual 替换。 |

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
| **Plugins → Agent** | ✅ WIRED | discovery 驱动装配：`PluginDiscovery(config).discover()` + `register_all`，两阶段 boot（`activate_boot` → restore → `activate_all`）。**8 个** builtin 经 entry_points。`/plugins` CLI。 |
| **Scheduler → Runtime** | ✅ WIRED | **Wave 3**：`AgentRuntime.start()` 后台 task 跑 `CronScheduler.start()`；`runtime.submit(prompt)` 给 cron job 入口；plugin_ctx 注入。 |
| **Runtime → Gateway** | ✅ WIRED | **Wave 3**：`AgentRuntime.start()` 绑 `gateway_registry.set_inbound_handler(self.handle_inbound)` + `start_all()`；Web/GatewayPlugin/CLI 共用同一套生命周期。 |
| **CLI 单事件循环** | ✅ WIRED | **Wave 3**：`_setup_agent` 改 sync 返未启动 Runtime；`repl()` 内 `await runtime.start()` / `finally: await runtime.stop()`；全文件仅一处 `asyncio.run(repl())`。 |
| **TUI** | ❌ NOT WIRED | `tui.py` 占位已删（T1 `ab20c07`），Phase 7 用 textual 真实现。 |
| **Web → Agent** | ❌ NOT WIRED | `/chat` 返回 `"coming soon"`。Phase 7。 |
| **SubAgent** | ❌ NOT WIRED | `task_tools.py` 基础实现，多代理协作未完全打通。Phase 7。 |

---

## 汇总

| Status | Count | 说明 |
|--------|-------|------|
| 🟢 REAL (可用) | 36 | 生产级或基本可用的独立模块（Wave 3 +1：`merco/gateway/` 完整 + `merco/core/runtime.py` AgentRuntime） |
| 🟡 PARTIAL (部分) | 2 | web/app.py / web_tools / task_tools（mcp_tools stub 已删） |
| 🔴 SKELETON (骨架) | 0 | tui.py + 2 个 gateway stub 均已删（Wave 3 + 去债 T1） |
| ❌ NOT WIRED (未集成) | 3 | TUI / Web → Agent / SubAgent（Scheduler→Runtime 与 Gateway 经 Wave 3 已 ✅） |
| **CLI 测试** | **94** | 9 个测试文件，覆盖 Dashboard / PromptArea / commands / lifecycle / REPL errors |
| **Plugin 测试** | **新增** | test_discovery / test_spec / test_manager / test_plugin_base / test_plugin_integration + 8 个 builtin 插件测试（含 Gateway） |
| **Gateway 测试** | **新增** | test_webhook + Runtime gateway 集成（`36f2293`） |
| **去债** | ruff 498→0 | `ruff check .` 0 error + `ruff format --check .` 0 diff；pre-commit 强制门；pyproject.toml `[tool.ruff]` 零改动 |
| **总测试** | **999 passed / 0 skipped / 0 failed** | Wave 3 → 去债 → 测试跳过修复 后全量 |

## 下一步（按优先级）

> **生态已收敛**：插件/模型/gateway 三大动态化完成，代码零技术债（ruff=0 + pre-commit），999 测试全绿。下一步不再围绕"接上去"，而是围绕"用起来更聪明"。

### 下一站候选方向：`Self-Improving Agent Loop`（prompt-level 自进化）

详细设计见 `references/next-focus.md`（决策中→下一步进 brainstorming）。核心机制：
- 订阅 `tool.error` / `conversation.turn` / `llm.chat` → `FeedbackDetector` 识别触发条件（连续 N 次同 tool 失败 / 单次 token 超阈值 / 用户反复纠正）；
- `Improver` 调 LLM 看具体失败 case，生成"应该怎么做"的 prompt-level 教训，写到 Memory（`source=system` priority=1）；
- 下次 `agent.run` → `HybridRecaller` 自动召回"经验" → 注入 system prompt；
- `fail-soft` 兜底（Improver 任何步骤失败 log + 跳过，不阻塞主循环）；
- 可控：默认 opt-in（`config.self_improver_enabled = False`），`/report` 显示已学 N 条，`/lessons` 列出，`/forget` 可清。

**为什么是这个方向**（见 `next-focus.md`）：架构复用率最高（Observer/Memory/Hook/Pipeline 零新基础设施）、merco 独家路径（hermes/openclaw/opencode 都没有 prompt-level 自进化）、不破坏现有架构（增量加 `SelfImprover`）、可见价值（用户用越久 agent 越懂自己）。

### 其他长期候选（暂缓）

| 候选 | 优先级 | 原因 |
|------|--------|------|
| Multi-Modal Context 引擎 | 低 | scope 大、依赖重，三家对标都没把它当核心 |
| Agent Composition (子 agent 编排) | 低 | 工程量大、各家都在做、无差异化 |
| TUI 实现（textual 替换占位） | 中 | Phase 7，但 Web 优先级可能更高 |
| Web 对接 Agent | 中 | `/chat` 真接通 `AgentRuntime.submit()`；可复用 Wave 3 Runtime |
| Docker 沙箱 | 中 | Phase 6 容器化路线，与 bubblewrap/firejail 一起排期 |
| SubAgent 多代理协作 | 中 | `task_tools.py` 完整化；需要 spec |
| LLM 摘要上下文压缩 | 中 | `CompressProcessor._summarize` 对接真实 LLM；当前为空 |

### 持续

- **agent.py 拆分** — 1186 行太重，StreamingProvider / NonStreamingProvider 可独立文件（Wave 2 已抽 `core/llm/response.py`，但 agent.py 仍有遗留 inline 逻辑）
- **PyPI 发布** — 发布 v0.4.0（插件/模型/gateway 动态化 + 代码债清零）并写 changelog
- **补充端到端测试** — 真实 LLM 的集成测试（当前 999 测试均为 mock/units）
