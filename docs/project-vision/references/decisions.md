# 关键决策记录

| 日期 | 决策 | 原因 |
|------|------|------|
| 2026-05-20 | Bug 修复必须走根因流程 | 表面修复（加 except: pass、调用方 try/catch 掩盖）只会延迟爆炸，且偏离项目 MVP 目标。加入 project-vision SKILL.md 强制遵守。 |
| 2026-05-20 | 采用 Python 3.12+ | 现代语法特性，asyncio 支持完善 |
| 2026-05-20 | 使用 uv 作为包管理 | 速度快，依赖解析优秀 |
| 2026-05-20 | 混合架构设计 | 结合两家框架优势，精简冗余 |
| 2026-05-20 | skill 源文件放 docs/，渐进式多文件披露 | 入口精简，详细内容按需读取；agent 同步副本由 gitignore 排除 |
| 2026-05-20 | 根目录 openmercury.json 不入库 | 本地开发配置，模板在 config/openmercury.json.example |
| 2026-05-20 | config 反序列化补全 api_key/base_url | 原 _from_dict 漏字段导致对接非 OpenAI 厂商时 base_url 丢失 |
| 2026-05-20 | 5 处关键集成链路标记为最优先 | 代码已完成但调用链缺失：Sandbox→Tools, Hooks→Agent, Observability→Agent, Memory→Sessions, Scheduler→Runtime |
| 2026-05-21 | 全链路调试日志系统 | Agent 循环、LLM 请求/响应、工具调用/返回均注入 logger.debug；CLI 新增 `--debug` 开关；API 错误记录状态码和请求体大小。 |
| 2026-05-21 | 重试策略参数化为 `retry_delays` | 核心 LLMClient 不应耦合任何 provider。改为：SDK 重试关闭（max_retries=0），新增 `retry_delays` 参数（默认 (2,4)），chat()/chat_stream() 使用配置化延迟统一处理。provider 特定行为通过配置层传入。 |
| 2026-05-21 | 重试策略扩展为 429 + 5xx | 510 错误未纳入重试。改为：捕获 `APIStatusError`，429 和所有 5xx 均可重试，4xx 不重试。 |
| 2026-05-21 | 新增请求冷却 `cooldown` 参数 | LLMClient 新增 `cooldown`（默认 1s），成功请求后强制等待，防止连续请求触发网关频控。Zero-cost for generous providers, safety net for strict ones。 |
| 2026-05-21 | tool_calls 格式修正为 OpenAI 标准 | 原格式 `{id, name, arguments}` 在 MiniMax-M2.5 上报 400。改为标准格式 `{id, type:"function", function:{name, arguments}}`。Qwen3 容忍了简化格式，但严格实现的产品不认。 |
| 2026-05-22 | CLI 输出分区架构：rule 分隔 + Markdown 渲染 | 输入/输出界限不清晰。采用 `console.rule(style="dim")` 框出响应区，`Markdown()` 渲染回复。工具调用走 stderr。不要 spinner——第一条输出自证"在干活"。 |
| 2026-05-22 | LLM 中间文字保留 | LLM 返回 tool_calls 时可能同时有文字（如"让我查询..."），原硬写 `content=""` 丢弃。改为 `response.get("content", "")` 保留渲染。不强制 prompt 要求 always comment。 |
| 2026-05-22 | readline prompt 用 `\x01`/`\x02` 包裹 ANSI | `input()` 的 ANSI 颜色码需用 readline 的 `RL_PROMPT_START_IGNORE`(`\x01`) 和 `RL_PROMPT_END_IGNORE`(`\x02`) 包裹，否则 prompt 宽度计算错误。 |
| 2026-05-22 | prompt 归还 `input()` 管理，不用 Rich 打印 | Rich 的 `console.print` 输出 ANSI 码后 readline 不知自己在哪行，导致光标越界删除。颜色通过 `input(prompt_string)` 中原生 ANSI 实现。 |
| 2026-05-22 | 工具异常喂回 LLM 自愈，不硬停 Agent | 工具执行出错原直接 propagate → agent 崩溃。改为 `ToolRegistry.execute()` 统一 try/except：`TypeError` 返回结构化 `{error, available_params, received_params}`，通用异常返回 `{error}`。所有错误以工具结果形式喂给 LLM，LLM 自己修正。此模式可扩展至权限拦截、超时等场景。 |
| 2026-05-23 | 收尾架构定稿：`_wrap_up_messages` + `_wrap_up_call` | 删 grace call（MiniMax 不配合），回到直接收尾。提示词收敛为一条 user 消息。预算到顶 + 批量截停共用同一对方法。tool_choice="none" best-effort，幻觉校验 + regex 清理兜底。版本号修正（v0.1.0）。 |