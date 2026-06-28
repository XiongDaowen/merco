# Bug 追踪

## 已修复

| 日期 | Bug | 根因 | 修复 |
|------|-----|------|------|
| 2026-05-20 | Role "tool" must follow tool_calls | agent.py 漏掉保存含 tool_calls 的 assistant 消息 | `_execute_tool_calls` 前补 `context.add(assistant_msg)` |
| 2026-05-20 | `surrogates not allowed` 崩溃 | bash 输出非 UTF-8 字节 + `json.dumps` 遇代理对 | decode(errors="replace") + `_clean_surrogates()` |
| 2026-05-20 | Ctrl+C 卡顿 | `run_in_executor` 阻塞 + 无信号处理 | 改用 `asyncio.to_thread` + SIGINT handler |
| 2026-05-21 | 429 限流风暴 | SDK 自动重试 0.4s/0.8s 太快，不读 Retry-After | `max_retries=0` + 手动 `retry_delays=(2,4)` |
| 2026-05-21 | 510 错误未重试 | 只捕获 `RateLimitError`，5xx 直接抛出 | 改为捕获 `APIStatusError`，429+5xx 全重试 |
| 2026-05-21 | MiniMax-M2.5 tool_calls 格式 400 | 简化格式 `{id,name,arguments}` 非 OpenAI 标准 | 转为 `{id,type,function:{name,arguments}}` |
| 2026-05-21 | 请求频发触发网关限流 | agent loop 无请求间隔 | 新增 `cooldown` 参数（默认 0.3s） |
| 2026-05-21 | 注释/代码里写了 SCNet | 核心模块不应知道 provider 名 | 全部清除，参数化 `retry_delays`/`cooldown` |
| 2026-05-22 | Ctrl+C 退出崩溃 + 两段确认 | 七次迭代 → 回退 `input()` + `exit_count` 计数器 | 信号 handler 只做动作不打印 |
| 2026-05-22 | `merco` 必须带子命令才能启动 | `run` 是 `@app.command` | 改为 `@app.callback(invoke_without_command=True)` |
| 2026-05-22 | 工具参数显示为 `\uXXXX` | `json.dumps` 默认 `ensure_ascii=True` | 改为 `ensure_ascii=False` |
| 2026-05-22 | max_tool_calls 硬编码 | `_max_tool_calls=10` | 改为配置项 `max_tool_calls`（默认 15） |
| 2026-05-22 | 响应 markdown 裸显 | `console.print(f"\n{response}")` | `console.print(Markdown(response))` |
| 2026-05-22 | 工具调用显示冗长 | `json.dumps()` 做显示 | `key=value` 拼接 |
| 2026-05-22 | CLI 方向键显现控制字符 | `input()` 未启用 readline | `import readline` |
| 2026-05-22 | LLM tool_calls 时文字被丢弃 | `assistant_msg` 硬写 `"content": ""` | `response.get("content", "")` |
| 2026-05-22 | 视觉层次混乱 | 所有输出混一起 | `console.rule()` 分框 |
| 2026-05-22 | max_tool_calls 超标硬停 | 不给 LLM 收尾机会 | `_wrap_up_messages` + `_wrap_up_call` |
| 2026-05-22 | 工具执行无进度 | 调用行打印后静默 | Live spinner + timing |
| 2026-05-22 | 退出清理分散 | `os._exit(0)` 跳过 finally | `_on_exit` LIFO 模式 |
| 2026-05-22 | 工具调用失败报错退出 | `TypeError` propagate → agent 崩溃 | registry.execute() try/except |
| 2026-05-22 | ReadFile 不支持 `offset` | execute() 不接 → `TypeError` | 加 `offset` 参数（1-indexed） |
| 2026-05-22 | Context compressed 断 tool 链 | `_truncate()` 切掉 tool_calls | 滑动窗口 + `_extend_to_chain()` |
| 2026-05-23 | 续命—LLM 幻觉工具调用 | 预算耗尽时 LLM 从记忆幻觉工具 | `tool_choice="none"` + `tools=[]` |
| 2026-05-23 | 续命 `role: "system"` 触发 MiniMax 400 | MiniMax 不允许中途 system | 回退 `role: "user"` |
| 2026-05-26 | `_is_transient_429` 悬空引用致 429 永不重试 | 函数从未存在，ImportError 被吞 | 删除引用，改状态码大类 + 关键字兜底 |
| 2026-05-26 | `_execute_tool_calls` 无 try/except | json.dumps 非可序列化穿透到 LLM 恢复 | try/except 兜底 str(result) |
| 2026-05-26 | Token 账本漏记 tool_calls | `msg_tokens()` 不看 tool_calls 字段 | 补 json.dumps(tool_calls) 计数 |
| 2026-05-26 | `total_tokens` 永远走估算 | `last_actual_tokens` 只给进度条 | 优先 API 实测值，回退估算 |
| 2026-05-26 | `llm_error()` WARNING 日志噪音 | 422 等仍打 WARNING + 全 JSON 裸显 | 删除 logger.warning |
| 2026-05-26 | `count_tokens`/`msg_tokens` 函数重复 | context.py 和 compressor.py 各一份 | 统一到 context.py |
| 2026-05-26 | `context.py` `ContextCompressor` 死壳 | 空壳 stub，真身在 memory/compressor.py | 删除死壳 |
| 2026-05-26 | `LLMClient` chat/chat_stream ~50行重复 | params/cooldown/retry 两处一模一样 | `_build_params` + `_request` 提取 |
| 2026-05-26 | LLM retry 两层重复 | LLM 层 + Agent 层各自重试，最坏 9 次 | LLM 层 retry 归零，RecoveryPipeline 唯一控制点 |
| 2026-05-31 | ToolGuard 用户规则优先级反转 | user 规则放在默认规则后，匹配顺序不对 | `user_rules` 在 `__init__` 中先添加，`_DEFAULT_RULES` 后 extend，user 规则在链首 |
| 2026-05-31 | SessionStore 启动恢复上下文丢失 | 旧实现只 load messages，不恢复 tool_call_id/tool_calls/reasoning 字段 | `Session.load()` 完整读取所有字段，agent._restore_context 灌入 |
| 2026-05-31 | Observer 双计数器重复累加 | `_merge_to_acc()` 后 acc 已含 live 值，下轮 save 又叠加 | 改为 save 时合并、reset live；restore 只读 acc |
| 2026-05-31 | Observer snapshot 不持久化 | 重启后累计统计全丢 | `session.metadata["observer"]` 存 snapshot，`save_metadata()` 持久化到 SQLite |
| 2026-05-31 | MiniMax 流式不返回 usage → 进度条为 0 | 流式 response.usage 为 None，`last_actual_tokens=0` | Token fallback：usage 缺失时 `est_tk(content+reasoning)` 估算 |
| 2026-05-31 | OpenAI/Anthropic cache 字段名不同 | OpenAI `cached_tokens`、Anthropic `cache_read_tokens` | `_extract_usage` 统一字段映射，`cached_tokens or cache_read_tokens` |
| 2026-05-31 | openai 缺失导致测试 import 失败 | `from openai import AsyncOpenAI` 在 llm.py 顶部 | openai import 延迟到 `LLMClient.__init__` |
| 2026-05-31 | edit_file Live spinner 覆盖确认提示 | Rich Live 渲染覆盖 confirm_edit 的 y/N 提示 | 交互式工具（edit_file）跳过 Live spinner |
| 2026-05-31 | think tag 残留 content | DirectFieldStrategy 命中后 ThinkTagStrategy 没跑 | `_strip_think_tags` 兜底清理 |
| 2026-05-31 | read_file 大文件阻塞 | `f.readlines()` 一次读完 100MB 文件 | 流式逐行迭代，读到 limit 即停 |
| 2026-05-31 | diff 全量并排+全量染色噪音 | 1 行改动显示 1000 行 diff | SequenceMatcher 对齐 + 上下文裁剪 ±3 行 + 仅变色变更行 |
| 2026-06-11 | 思考内容渐进泄漏到 content，重启多次后模型空回复 | 流式路径 `_parse_chunk` 缺 `_strip_think_tags`（非流式有），`extract_from_delta` 的 fallback 在策略返回 reasoning 但无 content 时，盲取 `delta.content` 导致思考文本被当作 content 存入 session。重启后污染上下文反馈给模型，渐进退化至完全空回复 | 三处加 `_strip_think_tags`：`extract_from_delta` fallback（2 处）+ `_parse_chunk` content 提取（1 处） |
| 2026-06-11 | 流式思考内容截断 | `Live.stop()` 前只刷新 content panel 不刷新 thinking panel，最后一帧思考文本未渲染 | `live.stop()` 前用最终 `reasoning_buf` 刷新 thinking panel |
| 2026-06-11 | 流式空 content panel 闪烁 | 模型 `</think>` 后产出的 `\n\n\n\n` 触发 content panel 懒创建但无可渲染文本 | `content_buf` 判断改为 `content_buf.strip()` |
| 2026-06-11 | 上下文用量始终显示 `—` | 流式 API 默认不返回 usage；`is_estimate=True` 时 `_fmt` 直接返回 `"—"` 丢弃了估算值 | 1) `include_usage: true` 默认传入；2) 估算时显示 `~8.5K` |
| 2026-06-11 | 压缩 checkpoint 过时导致重启丢失大量上下文 | checkpoint 创建后永不过期，session 从 283 条增长到 630 条，但每次重启只恢复旧的 summary + 4 条 tail，中间 340+ 条全丢 | 1) `_restore_context` 检测过时（新增 >20 条）→ 删除旧 checkpoint → 全量恢复 → 重新压缩；2) tail_count 从 2 提到 5 |
| 2026-06-11 | `ContextCompressRecovery` 压缩恢复永不生效 | `RecoveryContext` 有 `max_compress` 但缺少 `compress_count` 字段，访问抛出 AttributeError 被 `except Exception` 吞掉 | `RecoveryContext` 加 `compress_count: int = 0`，`RecoveryPipeline.attempt` 递增 |
| 2026-06-28 | 9 个预存测试失败 | 测试与实现语义不匹配（A 类）、ToolGuard mock 路径不正确（B+C 类）、压缩阈值断言过严（D 类） | 1) `_fmt(is_estimate=True)` 返回 `"—"；2) 导出 `_strip_think_tags`/`_clean_content`；3) Guard 测试直接注入 GuardMiddleware；4) 压缩断言 `<8` 改为 `<=8` |
| 2026-06-28 | 孤儿 tool_calls 导致 LLM 400 | 工具执行异常时 assistant 消息含 tool_calls 但 tool result 未保存，下次启动恢复后 LLM 报 `tool id not found` | `InterruptCleanupPipeline` 中 `InjectCancelMessages` 为孤儿 tool_calls 注入取消消息 |

## 待修复

| 日期 | 问题 | 描述 | 优先级 |
|------|------|------|--------|
| 2026-05-31 | scheduler 未启动 | CLI/Web 未实例化 CronScheduler | 中 |
| 2026-05-31 | Memory → Sessions 未集成 | SessionStore 不存 MemoryStore，recall 不接 system prompt | 中（Phase 5） |
| 2026-05-31 | Hooks handler 仍为 pass | lifecycle/chat/tool 三个 hooks 文件的 handler 未实现 | 低（Phase 6） |
| 2026-05-31 | compressor LLM 摘要未实 | `_summarize` 返回占位文本而非真实 LLM 摘要 | 低（Phase 6） |
| 2026-05-31 | context.compress() 未实 | ContextManager.compress() NotImplementedError | 低（Phase 6） |
| 2026-05-31 | WebSearch 骨架 | web_tools.WebSearch 返回 "not yet configured" | 中（Phase 3） |
| 2026-05-31 | mcp_tools 骨架 | MCPTool/MCPManager 全部 NotImplementedError | 中（Phase 3） |
| 2026-05-31 | task_tools 骨架 | TaskTool 无子代理派发 | 中（Phase 5） |
| 2026-05-31 | gateway/telegram discord 骨架 | 所有方法 pass | 低（Phase 5） |
| 2026-05-31 | tui.py "coming soon" | 仅有占位 print | 中（Phase 4） |
| 2026-05-31 | web/app.py "/chat" 返回 coming soon | 未对接 Agent | 中（Phase 4） |
| 2026-05-31 | builtin/skills 空目录 | 无内置 skill 文档 | 低（Phase 3） |
| 2026-05-31 | commands.py 3 行注释 | `/recall` `/fork` `/tree` 命令未实现 | 中（Phase 5） |
| 2026-05-21 | CLI 等待响应时无法输入 | REPL 同步阻塞在 `agent.run()` | 中 |
| 2026-05-22 | cooldown 硬编码在 agent.py | 应走配置层 | 中 |
| 2026-05-22 | 工具调用日志过多刷屏 | 15+ 调用占满终端 | 低 |
| 2026-05-22 | Ctrl+C 提示打断输入流 | 警告在当前行上方遮住 input() | 低 |
| 2026-06-07 | **Session 保存中途被打断** | Ctrl+C 快速按可能在 `session.save()` 执行中途被杀，导致数据不一致。修法：原子写入（先写 .tmp 再 rename）+ 启动时清理残留 .tmp | 中 |


---

## Phase 1 首次 CLI 调试记录 (2026-05-20)

### 工具调用 400 — tool 消息前无 tool_calls
根因: `agent.py._agent_loop()` 执行工具后追加 tool 消息，但从未追加含 tool_calls 的 assistant 消息。API 收到 system → user → tool 而非 system → user → assistant(tool_calls) → tool。
修复: `_execute_tool_calls()` 前补 `context.add({"role": "assistant", "content": "", "tool_calls": api_tool_calls})`。

### Surrogates 防御三层
- 源头: `decode("utf-8", errors="replace")` — bash_tools.py
- 序列化: `ensure_ascii=True` — agent.py  
- 发送前: `_clean_surrogates(messages)` — llm.py

### 请求放大 6 倍
SDK 自带 2 次重试 + Agent 层 3 次重试 = 1 次原始请求可能放大为 6 次。修复: SDK `max_retries=0`，由 Agent 统一控制。

### Ctrl+C 退出卡顿
`run_in_executor` 阻塞 input() 线程，Ctrl+C 信号到主线程但 executor 线程仍在等输入。改用 `asyncio.to_thread` + SIGINT handler。
