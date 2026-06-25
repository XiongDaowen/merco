# 项目进展

> 每次开发会话后更新。每次重大提交后必须根据提交内容同步更新。
> 最后更新: 2026-06-20

## 目标对标

对标 **Hermes Agent** (自学习/记忆/多平台网关)、**OpenClaw** (多平台/插件/定时任务)、**OpenCode** (TUI/Skill/MCP)，取其三家之长，构建更精简、更可落地的 AI Agent 框架。

## 当前状态

**阶段**: Phase 2 深入 | **焦点**: 插件系统 | **对标差距**: hermes 10 / openclaw 10 / merco → 10

### 本次会话更新 (2026-06-20)

- **插件系统（新功能）**: merco 架构升级为插件一等公民，构建可扩展的插件体系。
  - **Plugin 基类 + PluginContext**: `merco/plugins/base.py` — Plugin ABC（`activate`/`deactivate` 生命周期），PluginContext 暴露 9 个扩展点（hooks、tool_registry、prompt_builder、recovery_pipeline、result_pipeline、memory_save_pipeline、recaller、config、observer），便捷方法 `on()`/`register_tool()`/`add_prompt_chunk()`/`add_processor()`/`add_recaller()`
  - **PluginManager 生命周期管理**: `merco/plugins/manager.py` — register/activate/deactivate/activate_all/deactivate_all，激活失败隔离（单个插件异常不影响其他），`plugin.activated`/`plugin.error`/`plugin.deactivated` 事件 emit，按 config `enabled` 字段选择性激活
  - **Superpower 示例插件**: `merco/plugins/builtin/superpower/plugin.py` — 注册 SuperpowerHintChunk prompt 注入 + 订阅 `agent.start`/`tool.error` 事件，展示插件如何扩展 Agent 能力
  - **Config 字段 + Observer 集成**: `MercoConfig.plugins` dict 字段（序列化/反序列化），Observer 订阅 `plugin.activated`/`plugin.error` 事件追踪插件活动计数
  - **Agent 启动装配**: `merco/core/agent.py` — `__init__` 构造 PluginContext + PluginManager，注册 SuperpowerPlugin 内置插件，`activate_all()` 激活所有 enabled 插件
  - **CLI /plugins 命令**: `cli/commands.py` — 列出所有已安装插件及状态（已激活/未激活/已禁用），group="system"
  - **测试覆盖**: 12 个新测试（4 基类单测 + 5 PluginManager 单测 + 3 端到端集成测试），全部通过

### 本次会话更新 (2026-06-16)

- **集成测试补全（新功能）**: +8 个集成测试覆盖 6 个场景：
  - Context 压缩 + Session fork on compress
  - Memory recall 注入 system prompt 端到端 + HybridRecaller 真实数据
  - Memory save 全链路 + `memory.saved` 事件
  - RecoveryPipeline 重试（500 错误 → 第二次成功）
  - Hook 事件计数 during loop
  - MCP tool calling 端到端
  - 全部用 MockLLMClient + test_agent fixture，零网络依赖

### 本次会话更新 (2026-06-15)

- **Memory → Sessions 打通（新功能）**: 解决"存"和"什么时候存"两个空缺。召回链路早已通（HybridRecaller + FTS5 + MemoryRecaller），本次补齐保存侧。
  - **保存链（MemorySavePipeline）**: `merco/memory/save_pipeline.py` — 统一保存链，处理器模式 `SourceEnricher → DedupProcessor → Store`。`SOURCE_PRIORITY` (user=3 > extracted=2 > system=1) 保证显式 /remember 永远不被自动抽取覆盖。`SaveItem` dataclass + `MemorySource` Literal。
  - **触发策略（MemorySaveStrategy）**: `merco/memory/strategy.py` — 监听 Hook 事件，构造 SaveItem 喂 Pipeline。
    - `ExplicitRememberStrategy` 监听 `command.remember` — 同步，CLI 触发即存
    - `SessionEndExtractStrategy` 监听 `session.destroy` — opt-in，LLM 抽取 1-3 条 insight，fail-soft（LLM 失败/JSON 非法不抛）
  - **Agent 装配**: `merco/core/agent.py` 启动时构造 `memory_save_pipeline` + strategies，按 config opt-in 注入 extract 策略
  - **Observer 接入**: 订阅 `memory.saved` 事件 → `_live.increment("memories_saved")`，`/report` 显示
  - **CLI 命令（group="memory"）**:
    - `/remember <text>` — 显式存记忆（支持 `key=xxx` 显式 key 和 `key=value` 简写）
    - `/memories [tag]` — 列出所有记忆（可选 tag 过滤）
    - `/forget <key>` — 删除记忆（不存在静默 no-op）
  - **Config 字段**: `memory.auto_extract_on_session_end` (默认 False) + `memory.extract_max_per_session` (3) + `memory.extract_min_messages` (5)
  - **测试覆盖**: 16 个新单测 + 3 个端到端集成测试（Hook → Strategy → Pipeline → Store → Observer 全链路 + dedup 优先级验证）
  - **设计模式**: 策略模式（Strategy ABC）+ 管道模式（Pipeline + Processor 链）+ 事件订阅（HookRegistry 已成熟）
  - **写入重试机制**: `save_message` 对 `sqlite3.OperationalError` 重试 3 次（0.1s/0.2s/0.3s 递增退避），全部失败抛 `SessionWriteError` + 日志告警
  - **备份恢复机制**: `backup()` / `restore_from_backup()` / `delete_backup()`，WAL checkpoint 一致性保证，压缩前自动备份+成功删备份
  - **启动完整性检查**: `check_integrity()` (PRAGMA integrity_check) + `startup_check()`，损坏自动从备份恢复
  - **事务保证**: `INSERT messages` + `UPDATE sessions.message_count` 同一事务
- **Agent 压缩前备份**: `_compress_context` 入口 `backup()`，try/except/else 包裹压缩体 — 失败保留备份，成功删备份
- **测试覆盖**: `tests/memory/test_session_store.py` +5 个测试（retry 真实触发 / backup 创文件 / restore 恢复数据 / integrity 正常 / max retries 抛异常），全部通过

### 本次会话更新 (2026-06-13)

- **ToolGuard 架构重构（职责分离）**: 解决双重确认和 stdin 竞争问题。
  - ToolGuard 只做决策，返回 `GuardResult(action=ALLOW/DENY/ASK)`
  - 移除 `_confirm`、`_render_*` 等交互方法（职责移到 Agent 层）
  - Registry 抛出 `GuardConfirmationRequired` 异常
  - Agent 层处理确认交互，展示 Panel + 获取用户输入
- **Sandbox → ToolRegistry 打通**: 在 `ToolRegistry.execute()` 统一调用 ToolGuard。
- **think tag 泄漏根因修复**: `_strip_think_tags` 增加单独标签清理，`THINK_TAG_PAIRS` 统一配置。

### 本次会话更新 (2026-06-11)

- **流式 think tag 泄漏修复**: 流式路径 `_parse_chunk` 和 `extract_from_delta` 共 3 处缺 `_strip_think_tags` 清理（非流式有），导致思考文本泄漏到 content → 存入 session → 重启后污染上下文 → 渐进退化至空回复。修复：三处加 `_strip_think_tags()`，流式/非流式 content 清理一致。
- **压缩 checkpoint 过时检测**: checkpoint 创建后永不过期，session 从 283→630 条但每次重启只恢复旧 summary+4 条 tail。修复：`_restore_context` 检测 `len(all_msgs) > original_count + 20` → 删除旧 checkpoint → 全量恢复 → 重新压缩。`tail_count` 从 2 提到 5（保留 10 条消息）。
- **流式 UI 修复**: 空白 content panel（`content_buf.strip()` 过滤）、思考截断（`live.stop()` 前最终刷新 thinking panel）、上下文用量显示 `~8.5K` 而非 `—`。
- **RecoveryPipeline 修复**: `RecoveryContext` 缺 `compress_count` 字段导致 `ContextCompressRecovery` 永不生效 + `_is_retryable_llm_error` 新增 413 + context-too-large 关键字 + `WaitRecovery` 跳过 413（等待无法缩小上下文）。测试 11 个。
- **内置 Skill 自动安装**: `merco/skills/builtin/merco/SKILL.md` 随 wheel 分发，`install_builtin_skills()` 在 `merco setup` 和首次启动时复制到 `~/.config/merco/skills/`。
- **Superpowers 技能集成**: 安装 14 个 superpowers 技能（TDD、debugging、subagent、code review 等）。

### 本次会话更新 (2026-05-29)

- **Memory 召回（新功能）**: `Recaller` 协议 (`BaseRecaller` ABC) → `FTS5Recaller`（调 SessionSearch）+ `MemoryRecaller`（调 MemoryStore）→ `HybridRecaller` 聚合/排序/去重/截断/缓存。`Agent._build_system_prompt()` 末尾自动注入召回（3条×300字≈600 tokens）。`/recall` CLI 命令手动搜索。配置项：`memory.recall_enabled/limit/max_chars/threshold`。测试 23+7+16=46 个。
- **memory config 重构**: `memory_enabled/memory_path` 移入 `memory` 嵌套对象，与 recall 配置统一。`_from_dict` 加 isinstance 守卫防非 dict 值 crash。
- **会话 Fork/分支（新功能）**: `SessionStore.clone_session()` 原子深克隆 + `get_children()` 子会话查询。`Session.fork()` 工厂方法。`Agent._compress_context` 压缩前自动 fork 归档。`/fork` CLI 命令手动分支 + `/tree` 分支树查看。配置：`session.fork_enabled` + `session.fork_auto_on_compress`。测试 15 个。

### 本次会话更新 (2026-06-07)

- **流式 Content 输出（新功能）**: `stream_content` 配置项控制是否流式输出 content。流式时使用纯文本（`[dim]...[/dim]`），完成后切换为 Markdown Panel。解决了长内容输出时 Rich Markdown 渲染卡顿问题。
- **渲染节流优化**: `stream_render_interval` 从 50ms 改为 300ms（4fps），content 和 reasoning 统一节流。消除终端闪烁，长文本流式更流畅。
- **Content Panel 懒初始化**: content_panel 在首个 content chunk 到达时才创建，避免空面板闪烁。
- **Live+Group 单实例架构**: 统一使用一个 Live 实例管理 thinking_panel + content_panel，避免双 Live 冲突。
- **空回复处理**: `stream_content=False` 时正确打印最终 content，不重复、不丢失。
- **集成测试**: 新增 10+ 个流式输出边界测试（空回复、工具调用、transient 模式等）。

### 本次会话更新 (2026-06-05)

- **SKILL 案例 2 根因 1 修复（进度条"反降"）**:
  - 启动时进度条显示估算值（17K），第一次 API 响应后切换成实测（6.7K），用户看到"反降"
  - 修法：第一次 API 响应前显示占位 `—/62.5K` 而非估算值
  - 实现：复用 `get_context_stats()` 已有的 `is_estimate` 字段；`_fmt` 加默认参数保持向后兼容
  - 提交：`57ccb83`（第一版修错：只判 n==0）+ `c137185`（第二版修对：is_estimate 一律占位）

- **SKILL 案例 2 根因 D 修复（_restore_context 保留空 tool_call_id）**:
  - provider（如 scnet.cn）流式首 chunk 不发 `tool_call.id`，Ctrl+C 在 id 到达前中断 → tc_buf[id]=""
  - InterruptCleanupPipeline 注入"取消 (Ctrl+C)" tool 消息时把 `""` 写进 session
  - 重启后 `_restore_context` 用 `if msg.get("tool_call_id"):` 过滤掉 `""` → 消息链断 → 下轮 API 报 400
  - 修法：两行 `if "tool_call_id" in msg:` 替换 truthy 过滤 —— key 存在就赋值，不管真假
  - 提交：`1ebd698`

- **遗留未修**：根因 A (`context.add()` 不清零 last_actual_tokens) + 根因 C (`_restore_context` 不重建 _overhead_tokens) —— A/B 实际影响已被根因 1 修复屏蔽，C 窗口仅限"启动到第一次 run"几秒，run 入口已有 set_overhead 补救。严格修需把 `_restore_context` async 化，影响 6 处调用点，搁置

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
| `session_store.py` | 🟢 REAL | SQLite 会话持久化，sessions + messages 表，WAL 模式。 |
| `save_pipeline.py` | 🟢 NEW | MemorySavePipeline + SaveItem + SourceEnricher + DedupProcessor。`SOURCE_PRIORITY` 保护 user > extracted > system。 |
| `strategy.py` | 🟢 NEW | MemorySaveStrategy ABC + ExplicitRememberStrategy + SessionEndExtractStrategy (LLM 抽取 fail-soft)。|

### Other Modules

| Module | Status |
|--------|--------|
| `hooks/` | 🔴 SKELETON — 未集成 |
| `sandbox/` | 🟢 POLISHED — diff split view + show mode + ToolGuard guard。未集成到 Tools |
| `scheduler/` | 🟢 REAL — CLI 未启动 |
| `observability/` | 🟢 REAL — Observer 已接入 Agent（中断/Report），hooks 未触发 |
| `mcp/` | 🟢 NEW — MCPServerManager stdio+HTTP 传输，工具发现+注册，沙箱集成 |
| `gateway/` | 🔴 SKELETON |

### merco/plugins/ — Plugin System

| File | Status | Details |
|------|--------|---------|
| `base.py` | 🟢 NEW | Plugin ABC（activate/deactivate）+ PluginContext（9 扩展点 + 5 便捷方法）。|
| `manager.py` | 🟢 NEW | PluginManager 生命周期管理：register/activate/deactivate/activate_all，失败隔离，事件 emit。|
| `builtin/superpower/plugin.py` | 🟢 NEW | SuperpowerPlugin 示例：prompt chunk 注入 + 事件订阅。|

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
| Hooks → Agent | ✅ WIRED | agent.start/stop, session.create/destroy, message.receive, tool.before_execute, context.compact 已 emit |
| Sandbox → Tools | ✅ WIRED | `Registry.execute()` 调 `ToolGuard.check()`，SecurityChecker 正则兜底 + 规则链 ask/deny/allow。 |
| Observability → Agent | ✅ WIRED | Observer 订阅所有事件：llm.chat, tool.after_execute, tool.error, conversation.turn, agent.interrupted, agent.start/stop, context.compact |
| MCP → Agent | ✅ WIRED | MCPServerManager 接管 MCP config 加载 + 工具注册 + 沙箱守卫。 |
| Memory Recall → Agent | ✅ WIRED | `_build_system_prompt` 自动注入 FTS5 召回结果。 |
| Memory Save → Agent | ✅ WIRED | Agent 启动装配 MemorySavePipeline + Strategies，/remember 触发保存，session.destroy 触发 LLM 抽取。 |
| Plugin → Agent | ✅ WIRED | Agent.__init__ 装配 PluginManager + SuperpowerPlugin，activate_all 激活 enabled 插件，/plugins 命令查看状态。 |

---

## 汇总

| Status | Count |
|--------|-------|
| 🟢 POLISHED | 11 |
| 🟢 NEW | 8 |
| 🟢 REAL | 8 |
| 🟡 PARTIAL | 6 |
| 🔴 SKELETON | 8 |
| ✅ WIRED | 5 |

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
| 插件系统 | ✗ | ✗ | ✓ | **✓ (新增)** |

**总分**: hermes 10 / opencode 7 / openclaw 10 / **merco 10**

## 已知问题 / 技术债

| # | 位置 | 问题 | 修复方案 | 优先级 |
|---|------|------|----------|--------|
| 1 | `core/agent.py` StreamingProvider checkpoint | `__anext__()` I/O 等待时 CancelledError 不执行 checkpoint，partial content 丢失 | 改用 `except CancelledError` 统一拦截 | 低 |
| 2 | `core/agent.py` StreamingProvider reasoning 渲染 | ~大段推理文本每次 chunk 重建 Panel，卡顿后跳出一堆~ | ✅ 已修复：`stream_render_interval` 限流 + `_build_reasoning_panel` 统一构建 | — |
| 3 | `core/llm.py` / `agent.py` reasoning 泄漏怀疑 | 用户观察到历史 reasoning 出现在 thinking 面板，代码审查未发现客户端泄漏路径 | 已在 5 处加日志打桩，`--debug` 观察 | — |

## 下一步（按优先级）

1. **Scheduler → Runtime** — CronScheduler 已有，接入 CLI 启动时加载 + 按时触发
2. **TUI 实现** — Textual 重写 REPL，多会话切换/分支树/记忆管理
3. **集成测试补全** — mock LLM 的 Agent-Loop 全覆盖（压缩/恢复/工具调用/记忆召回） ✅ 已完成
4. **插件系统** ✅ 已完成 — Plugin 基类 + PluginManager + Superpower 示例 + 12 测试
5. **通一个 Gateway** — Telegram 端到端（Bot API + webhook/polling）
6. **Memory SecretFilterProcessor** — 检测 API key/密码/身份证号写入（YAGNI 预留）
7. **MemoryStore backend 抽象** — 支持 SQLite 后端（YAGNI 预留）
