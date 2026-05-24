# 关键决策记录

| 日期 | 决策 | 原因 |
|------|------|------|
| 2026-05-26 | LLM retry 统一到 Agent RecoveryPipeline | LLM 层和 Agent 层各有一套 retry，重复且策略分散。改为 LLM 纯传输（不重试），Agent RecoveryPipeline 唯一控制点。llm.py 330行→200行。 |
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
| 2026-05-20 | 根目录 openmercury.json 不入库 | 模板在 config/。 |
