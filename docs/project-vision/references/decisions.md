# 关键决策记录

| 日期 | 决策 | 原因 |
|------|------|------|
| 2026-07-24 | 非 UTF-8 输出测试改用 `cat` 二进制文件替 `printf '\xff\xfe\xfd'`（`e7dd024`） | dash `/bin/sh` 的 `printf` 不支持 `\x` 十六进制转义，`printf '\xff\xfe\xfd'` 只输出字面反斜杠而非字节，断言 `assert "�" in stdout` 永不可能成立——这是真实死测不是过时跳过。改为把 `b"\xff\xfe\xfd"` 用 Python 写入 `tmp_path` 再 `cat`，无 shell 转义，稳定验证 bash 工具 `decode(errors="replace")` 从非法 UTF-8 产出 `�`。 |
| 2026-07-24 | 去债波：ruff 498→0 靠修根因而非关规则；`.pre-commit-config.yaml` 用本地 `uv run ruff` 钩子防回归（`3b495d9`..`d92d958`） | 用户强制无历史债务。ruff 配置一字未改（`select=["E","F","I","N","W","UP"]`, `line-length=120`），零靠修不靠禁。pre-commit 用项目 venv 内 `uv run ruff`（版本对齐），不下载独立 ruff——避免版本漂移导致本地与 CI 结果不一致。 |
| 2026-07-24 | F401 autofix 前先标注 side-effect import + fixture 再导出（`3b495d9`） | `ruff --fix --select F401` 会删有副作用的 import。`import cli.commands` 触发 `@cmd_registry.register` 装饰器 → 加 `# noqa: F401`（cli/main.py:449）；`tests/integration/conftest.py` `_isolation_services` fixture 再导出（pytest 按模块属性发现）→ `# noqa: F401`（autofix 曾误删致 52 集成测试挂）；`merco/sandbox/__init__.py` `_DEFAULT_RULES` 再导出 → 加进 `__all__`。顺序：noqa 先，再 autofix。 |
| 2026-07-24 | UP037 去注解引号全仓 `--fix --unsafe-fixes` 安全（`83f9b7c`） | 两条件同时成立才安全：(a) 所有带注解文件均有 `from __future__ import annotations`；(b) 全仓零运行期注解求值（Pydantic 在 pyproject 声明但从未 import，无 get_type_hints/BaseModel）。缺一则去引号会破坏运行期类型解析。 |
| 2026-07-23 | Wave 3：Scheduler 接入 AgentRuntime 生命周期宿主（`1c49854`） | AgentRuntime（merco/core/runtime.py）薄壳，持有 Agent + CronScheduler + GatewayRegistry；幂等 start/stop；`submit(prompt)` 编程/cron 入口、`handle_inbound(source, chat_id, message)` gateway 入口，二者都 → `agent.run()`。turn-loop 留在 agent.py 不搬。per-run 生命周期事件（agent.start/agent.stop 等）由 `Agent.run` 自 emit，宿主 teardown 不重复 emit。 |
| 2026-07-23 | Wave 3 单 session 降作用域：`handle_inbound` 只把 `message` 路由给 `agent.run`（`99b7342`） | 当前单会话模型，chat_id 多会话路由推迟。`handle_inbound(source, chat_id, message)` 保留 chat_id 参数做前向兼容但暂不用，只传 message，避免过早引入多会话状态。 |
| 2026-07-23 | Wave 3 CLI 单事件循环：`_setup_agent` 同步返回未启动 Runtime，`repl()` 内 start/stop（`09abde1`） | 原 `_setup_agent` async + 外层 asyncio.run 是双层循环。改为 `_setup_agent` 同步返回未启动 AgentRuntime；`repl()` 内 `await runtime.start()`、`agent=runtime.agent`、finally `await runtime.stop()`。全程单一 `asyncio.run(repl())`（cli/main.py:571）。 |
| 2026-07-23 | Wave 3：`GatewayAdapter` ABC（原 `BaseGateway`）+ `set_message_handler` 契约（`76219d6`） | 统一入口适配器契约：`set_message_handler` 存 `_message_handler`，抽象 `start`/`stop`/`send_message`。删旧 `handle_message`（拉模式），改推模式（registry 注入 handler）。WebhookGateway 作参考适配器（`ed8af45`，FastAPI/uvicorn，port=0 OS 分配，`actual_port` 从 `server.servers[0].sockets[0].getsockname()[1]` 提取）。 |
| 2026-07-23 | Wave 3：GatewayRegistry 每适配器 `_bound(chat_id, message, _name=name)` 闭包（`650c270`） | 循环变量 `name` 晚绑定会让所有适配器闭包绑到最后一个；`_name=name` 默认参在 def 时求值捕获本轮名字（3 适配器测试证明）。单 gateway start/stop 失败隔离（记日志不拖垮其它）。 |
| 2026-07-23 | Wave 3：`GatewayRegistry.register` 重名抛 ValueError（故意背离 ModelRegistry 静默覆盖，`650c270`） | gateway 是持有 live 资源（端口/连接）的条目，静默覆盖会泄漏资源；ModelRegistry 条目是无副作用元数据可覆盖。`get` 未命中抛 KeyError。 |
| 2026-07-23 | Wave 3：PluginContext 加 `gateway_registry` + `register_gateway()`（`f690a9f`）；GatewayPlugin 第 8 内置 priority=25（`29a6a14`） | 第三方入口适配器经便捷方法注入，与 Wave 2 `register_model_provider` 对齐。PluginContext 增至 23 属性 + 11 方法（原 20+4）。GatewayPlugin 自动注册 WebhookGateway。 |
| 2026-07-23 | Wave 3：删 5 个死文件（`97e70fc`, `ab20c07`） | `cli/tui.py`、`merco/tools/mcp_tools.py`（MCP 真身在 `merco/mcp/`，此为 stub 假实现）、`merco/gateway/{telegram,discord}.py`、`merco/scheduler/{delivery,jobs}.py`。无历史债务：删而非降级保留。 |
| 2026-07-23 | Wave 2：`ModelRegistry` 为模型层唯一真源，删旧 `PROVIDER_REGISTRY` dict + `ProviderInfo` + `_client.py` + `LLMClient`（`f27cc94`, `4951099`） | 旧 dict 注册表 + LLMClient 传输层职责混杂。新建 `ModelProvider` ABC + `ModelRegistry`（唯一真源）+ `ModelProviderInfo` dataclass。`select()` 独占凭据解析（env `key_env` 查找 + base_url 处理）。custom provider（如 opencode.ai）在 `select()` `KeyError` 时按 `ModelConfig(base_url=...)` 自动构造（base_url 为空时保留 typo 检测，`05e7bdf`）。无迁移别名（no-debt gate）。 |
| 2026-07-23 | Wave 1：编译期插件硬编码 → PluginDiscovery + PluginManager + PluginContext（`dd79bb3`..`b54c97b`） | 替换 agent.py:448-514 import+register 与硬编码激活序 534-545。PluginDiscovery 走 entry-points `merco.plugins` + 目录扫描；PluginManager 按 priority 拓扑激活（越大越早，`priority >= BOOT_PRIORITY(100)` 走 boot 阶段）；PluginContext 属性 + 便捷方法。8 个内置插件从硬编码 import 迁到 `pyproject.toml [project.entry-points."merco.plugins"]`，各自独立目录 `merco/plugins/builtin/{...}/plugin.py`。 |
| 2026-07-23 | 下一投入方向锁定为插件动态化三波路线（波1 地基 / 波2 模型层 / 波3 多入口） | 当前插件编译期硬编码（agent.py:448-514 import+register，激活顺序硬编码 534-545），无发现机制。先做动态加载地基（discover + manifest + 拓扑排序）+ 扩展点便捷方法一致化，再 ModelProviderRegistry，最后 Scheduler 接 Runtime + GatewayRegistry。详见 [plugin-dynamic-loading-plan.md](plugin-dynamic-loading-plan.md)。核实发现 P2 PermissionPolicy 已实现（guard.py:145-195），roadmap 文档滞后。 |
| 2026-07-21 | CLI UI 快照测试基于 Rich `Console(record=True)` + 双缓冲 (`get_markup()`) | 不用截图/ANSI 颜色码断言。markup 文本稳定（`[red]`/`[bold]`），跨终端不脆。`_CaptureConsole` 子类拦截 `print()` 保存原始 markup 到 side buffer。 |
| 2026-07-21 | `_run_one_turn()` 从 `run_repl()` 抽出为模块级函数 | 797 行巨型 while 循环无法单独测异常路径。抽出后 13 个异常路径测试直接覆盖；InputInterrupt 留在 `repl()`（依赖 `exit_count` 闭包）。 |
| 2026-07-21 | API 错误呈现：非 debug 模式零 WARNING + 每次 retry 一个完整 Panel | `logger.warning(exc_info=True)` 泄漏 stacktrace → 改为 `logger.info`（WARNING 阈值抑制）。Panel 不叠层：except 块 `console.print(build_error_panel(...))` 直接输出，不依赖 Live transient/static。 |
| 2026-07-21 | 流式 tool call 响应不重复打印 | `_dispatch_tool_calls()` 在 streaming 模式 Live 已显示后仍 `console.print(Panel(...))` → 加 `if not (streaming and stream_content)` 与 `_run_one_turn` 逻辑统一。 |
| 2026-07-21 | 错误响应用 `Text.from_markup` 替代 `Markdown` | `llm_error(e)` 返回 Rich markup 字符串（`[bold red]...[/bold red]`），Markdown 不渲染。`Text.from_markup` 正确渲染，红 Panel 显示完整错误详情。 |
| 2026-07-21 | Provider 不可注册时只需 base_url 显式填写 | `ModelConfig.resolve()` 对未注册 provider 只 warn 一行，不阻断。opencode.ai 这类代理直接写 `provider` + `base_url` 即可。 |
| 2026-06-03 | Skill 三状态计数 (REAL/PARTIAL/SKELETON + NOT WIRED) | 原五状态 (POLISHED/NEW/REAL/PARTIAL/SKELETON) 难以维护，三状态够用。Skill 副本与代码状态重对齐。 |
| 2026-06-03 | Recaller 协议/Session Fork 标记为 Phase 5 计划中 | `.merco/skills` 副本曾描述但代码未实现，避免误导用户。 |
| 2026-05-31 | Hooks 驱动可观察性（Observer + HookRegistry） | 原 metrics 直接埋点侵入式，新增指标改 5+ 文件。Hooks 解耦：业务代码只 emit，Observer/Metrics 订阅。Phase 6 加 MetricsCollector/AuditLogger 订阅点。 |
| 2026-05-31 | ToolGuard 30 条默认 ask 规则（不硬拦截） | 全 deny 阻断正常开发，全 allow 无意义。ask 模式：用户可加 deny 规则，30 条默认覆盖 rm/sudo/pip/docker 敏感点。ToolGuard.check() 接入 agent._execute_tool_calls 前。 |
| 2026-05-31 | SessionStore SQLite 替代 JSON 文件 | JSON 文件并发写丢消息 + 全文检索需遍历。SQLite WAL 模式支持并发读 + 单写，WAL 性能 > 默认 rollback。`FOREIGN KEY` 保证 messages 关联 session 完整性。 |
| 2026-05-31 | ProviderInfo dataclass 替代 dict 注册表 | dict-style 访问无类型提示，IDE 补全差。dataclass + `__getitem__` 向后兼容（PROVIDER_REGISTRY["openai"]["base_url"] 仍可用）。新平台一行注册。 |
| 2026-05-31 | Token 兼容 fallback（usage 缺失时估算） | MiniMax 流式不返回 usage，`total_tokens=0` 导致进度条为 0。`last_actual_tokens` 优先，非零采信；零时回退 `est_tk(content+reasoning)`。永不为 0。 |
| 2026-05-31 | Observer 累计公式 `acc + (live - last_merged)` | `_merge_to_acc()` 后 acc 已含 live 值，直接 acc+live 重复计数。三容器职责：acc 锚点（跨运行）/ live 实时（当前 run）/ last_merged 合并快照（防双计）。 |
| 2026-05-31 | Observer snapshot 存 session.metadata 字段 | 会话 SQLite 已有 metadata JSON 字段，Observer 状态随会话持久化。重启时 `_restore_context` 读 metadata → `observer.restore()` 恢复 acc。 |
| 2026-05-31 | openai import 延迟到 LLMClient.__init__ | 测试环境 conftest.py 需 import 其他模块，openai 缺失导致整个 agent 跑不起来。延迟 import 让单元测试不依赖 openai。 |
| 2026-05-31 | SkillViewTool 动态 describe() | 技能列表变更时无需改 system prompt。`describe()` 在 tool definition 调用时拼接当前可用技能。`check()` 有技能才显示（无技能时不暴露工具）。 |
| 2026-05-31 | 集成测试用 MockLLMClient | 真实 LLM 调用慢/贵/不确定。MockLLMClient 接收预设响应序列，conftest.py fixture 复用。集成测试 2 秒全过，CI 友好。 |
| 2026-05-31 | `_extract_usage` 多 provider 缓存采集 | 各 provider usage 字段不一致（OpenAI: `cached_tokens`、Anthropic: `cache_read_tokens`）。`_extract_usage` 统一字段映射：`cached_tokens or cache_read_tokens` 都采集，Observer 统计缓存命中率。 |
| 2026-05-26 | LLM retry 统一到 Agent RecoveryPipeline | LLM 层和 Agent 层各有一套 retry，重复且策略分散。改为 LLM 纯传输（不重试），Agent RecoveryPipeline 唯一控制点。llm.py 330 行→200 行。 |
| 2026-05-26 | 启动首页 Dashboard + 输入区 PromptDecorator 可组合架构 | 硬编码 f-string 和进度条无法扩展。Dashboard/DashboardSection 和 PromptArea/PromptDecorator 组合模式，新增条目只需继承 + .use()。 |
| 2026-05-26 | Token 账本优先 API 实测值 | `total_tokens` 此前永远走估算（含魔术数 tool*200）。改为优先 `last_actual_tokens`，回退估算。`msg_tokens()` 补 tool_calls 计数。 |
| 2026-05-26 | `_is_transient_429` 悬空引用改大类+关键字 | 函数从未存在，ImportError 被吞使 429 永不重试。改 HTTP 状态码大类（429+5xx）+ 消息关键字兜底。 |
| 2026-05-26 | Token 估算统一到 `core/context.py` | `compressor.py` 和 `context.py` 各有一份。合并到 `core/context.py`。 |
| 2026-05-26 | PromptBuilder 新增 TimeContextChunk | LLM 不知道当前时间，注入日期时间帮助判断文件时效。~25 token。 |
| 2026-05-26 | 删除 `context.py` 死壳 `ContextCompressor` | 真身在 `memory/compressor.py`，stub 是早期死代码。 |
| 2026-05-23 | 收尾架构定稿：`_wrap_up_messages` + `_wrap_up_call` | 删 grace call（MiniMax 不配合）。提示词收敛为一条 user 消息。tool_choice="none" + 幻觉校验 + regex 兜底。 |
| 2026-05-22 | 工具异常喂回 LLM 自愈 | `ToolRegistry.execute()` try/except：TypeError 返回结构化 error，通用异常返回 {error}。 |
| 2026-05-22 | CLI 输出分区架构：rule 分隔 + Markdown 渲染 | `console.rule()` 框响应区，`Markdown()` 渲染。 |
| 2026-05-22 | Context 压缩重写：滑动窗口 + 链完整 | 原 `messages[-10:]` 切掉 tool 链。改为 token 感知滑动窗口 + `_extend_to_chain()`。 |
| 2026-05-22 | LLM 中间文字保留 | tool_calls 时 LLM 可能同时有文字（如"让我查询..."），保留渲染。 |
| 2026-05-21 | 重试策略参数化为 `retry_delays` + 扩展为 429+5xx | SDK 自动重试太快，新增 cooldown 参数。现已废弃——retry 统一归 RecoveryPipeline。 |
| 2026-05-21 | tool_calls 格式修正为 OpenAI 标准 | `{id, type:"function", function:{name, arguments}}`。 |
| 2026-05-21 | 全链路调试日志系统 | Agent/LLM/Tool 均注 logger.debug；CLI `--debug` 开关。 |
| 2026-05-20 | Bug 修复必须走根因流程 + 同类全检 | 表面修复延迟爆炸。project-vision SKILL.md 强制遵守。 |
| 2026-05-20 | 采用 Python 3.12+ / uv 包管理 | 现代语法特性，asyncio 完善。 |
| 2026-05-20 | skill 源文件放 docs/，渐进式多文件披露 | 入口精简，详细内容按需读取。 |
| 2026-05-20 | 根目录 merco.json 不入库 | 模板在 config/。 |
