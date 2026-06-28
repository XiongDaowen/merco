# 关键决策记录

| 日期 | 决策 | 原因 |
|------|------|------|
| 2026-06-29 | 估算 token 显示 `~N` 前缀 | 流式 API 无法实时获取 usage，估算值用 `~` 前缀区分实测值（如 `~8.5K`），用户可据此判断精度 |
| 2026-06-28 | Async Agent Factory 统一初始化 | 原 `Agent.__init__` 双路径（直接/工厂），各插件在 `__init__` 中注册逻辑分散。改为 `Agent.create()` 工厂方法，插件注册集中，测试可替换为 MockAgent |
| 2026-06-28 | 预存测试失败全部修复 | 9 个失败根因明确（4 类），与 Phase 3/4 修改无关；修复后全量回归通过 |
| 2026-06-28 | InterruptCleanupPipeline 替代 `_inject_interrupted_tool_results` | 原方法分散在 agent.py，逻辑与中断处理耦合。Pipeline 模式支持可插拔处理器：InjectCancelMessages/TerminateSubprocesses/CloseMCPConnections/EmitInterruptHooks/SavePartialState |
| 2026-06-28 | `_strip_think_tags`/`_clean_content` 导出 | 测试需直接调用验证行为；`__all__` 明确公开接口 |
|------|------|------|
| 2026-06-15 | Memory 保存侧采用 Strategy + Pipeline + Hook 三模式组合 | Recall 链路（HybridRecaller）已通，保存侧需要同时支持多触发源（/remember CLI + session 结束 LLM 抽取）和多处理（dedup/filter/enrich）。直接调用 `store.save` 散落各处无法扩展。三模式各司其职：Strategy 监听事件构造 SaveItem、Pipeline 串联 Processor 链、Hook 解耦业务与可观察性/审计。新触发源扩展只需一个 Strategy 类。 |
| 2026-06-15 | SOURCE_PRIORITY = {user: 3, extracted: 2, system: 1} 保护显式 /remember | LLM 自动抽取的 extracted 永远不应覆盖用户显式存的记忆（用户明确说"我喜欢中文"，LLM 不该改成"用户偶尔用中文"）。`DedupProcessor` 在已有 key 时比较 source 优先级，新低则 skip。`DedupProcessor._infer_source` 从已有 tag 反推 source，应对未来读取老数据的场景。 |
| 2026-06-15 | SessionEndExtractStrategy 默认 opt-in (config.memory_auto_extract_on_session_end = False) | LLM 抽取消耗 token 且质量不可控，对小项目/开发环境是负担。默认关闭 + 文档提醒，让用户主动开启。`/remember` 显式存不存在任何疑虑。 |
| 2026-06-15 | LLM 抽取走 fail-soft (不阻塞 session.destroy) | 用户退出体验优先于记忆质量。LLM 网络/5xx/JSON 解析失败 → log warning + return，session.destroy 正常完成。`memory_extract_min_messages` 默认 5 也避免空会话浪费 token。 |
|------|------|------|
| 2026-06-07 | 流式 Content 纯文本 + 完成后切 Markdown | Rich Markdown 每次 chunk 重新解析全文，长内容卡顿。纯文本 `[dim]...[/dim]` 零解析开销，流式结束后一次性切 Markdown Panel。用户感知：流式时灰色文字，完成后变彩色 Markdown。 |
| 2026-06-07 | 渲染节流统一 300ms（4fps） | 原 50ms（20fps）闪烁严重，人眼感知 4fps 足够流畅。content 和 reasoning 共用 `stream_render_interval`，避免各自节流逻辑分散。 |
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
| 2026-06-03 | StreamingProvider CancelledError checkpoint 保留为设计 trade-off | async for 内 __anext__ I/O 等待时被取消会丢 partial content，窗口极小且用户主动取消，收益近零，低优先级。 |
| 2026-06-03 | LLMClient 统一 None 防护 + extra_params/headers 可配置 | _normalize_tool_calls 归一 tool_call 避免 str += None；extra_params 透传 top_p/seed 等；headers 支持 X-Title；stream_options 收流式 usage。 |
| 2026-06-03 | _normalize_tool_calls 不假设 tc.function 存在 | scnet 等 API 分 chunk 补全 function（首 chunk 无 function 字段），`func = tc.function; func.name if func else ""` 兼容。 |
| 2026-06-03 | 推理泄漏采用日志观察优先策略 | 先加 5 处 WARNING/DEBUG 日志打桩，`--debug` 运行观察；若无 WARNING 则判定为 provider 端行为，不改客户端代码。 |
| 2026-06-03 | MCPServerManager 支持 stdio + HTTP 传输 | stdio（子进程）+ StreamableHTTP（URL 远程）两种传输，工具发现 + 自动注册 + 沙箱集成。 |
| 2026-05-26 | LLM retry 统一到 Agent RecoveryPipeline | LLM 层和 Agent 层各有一套 retry，重复且策略分散。改为 LLM 纯传输（不重试），Agent RecoveryPipeline 唯一控制点。llm.py 330 行→200 行。 |
| 2026-05-26 | 启动首页 Dashboard + 输入区 PromptDecorator 可组合架构 | 硬编码 f-string 和进度条无法扩展。Dashboard/DashboardSection 和 PromptArea/PromptDecorator 组合模式，新增条目只需继承 + .use()。 |
| 2026-05-26 | Token 账本优先 API 实测值 | `total_tokens` 此前永远走估算（含魔术数 tool*200）。改为优先 `last_actual_tokens`，回退估算。`msg_tokens()` 补 tool_calls 计数。 |
| 2026-05-26 | `_is_transient_429` 悬空引用改大类+关键字 | 函数从未存在，ImportError 被吞使 429 永不重试。改 HTTP 状态码大类（429+5xx）+ 消息关键字兜底。 |
| 2026-05-26 | Token 估算统一到 `core/context.py` | `compressor.py` 和 `context.py` 各有一份。合并到 `core/context.py`。 |
| 2026-05-26 | PromptBuilder 新增 TimeContextChunk | LLM 不知道当前时间，注入日期时间帮助判断文件时效。~25 token。 |
| 2026-05-26 | 删除 `context.py` 死壳 `ContextCompressor` | 真身在 `memory/compressor.py`，stub 是早期死代码。 |
| 2026-05-28 | WebSearch 接入 DuckDuckGo（免费/无 key）| `check()` 返回 False 导致工具隐藏。接入 API 实现真正搜索。保留 `source` 参数扩展口，后续 Google/SearXNG 按 Provider 注册表模式接入。 |
| 2026-05-28 | openai 导入延迟到 `LLMClient.__init__` | 测试环境无 openai 时 import agent 模块失败。延迟到类实例化时导入。 |
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
