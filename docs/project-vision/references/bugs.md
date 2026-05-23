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
| 2026-05-21 | 请求频发触发网关限流 | agent loop 无请求间隔，工具执行后立刻发下一请求 | 新增 `cooldown` 参数（默认 0.3s） |
| 2026-05-21 | 注释/代码里写了 SCNet | 核心模块不应知道 provider 名 | 全部清除，参数化 `retry_delays`/`cooldown` |
| 2026-05-22 | Ctrl+C 退出崩溃 + 两段确认 | 七次迭代：`loop.stop()`→crash→exit_flag→不生效→SIG_DFL→杀进程→`_readline()`→WSL不稳→最终回退到 `input()` + `exit_count` 计数器。第一次 Ctrl+C 提示，第二次退出；正常输入重置计数。 | 信号 handler 只做动作不打印；`input()` 是工业标准不手搓替代 |
| 2026-05-22 | `openmercury` 必须带子命令才能启动 | `run` 是 `@app.command`，直接敲只显示 help | 改为 `@app.callback(invoke_without_command=True)`，提取 `_setup_agent()` |
| 2026-05-22 | 工具参数显示为 `\uXXXX` 转义符 | `json.dumps(arguments)` 默认 `ensure_ascii=True` | 改为 `ensure_ascii=False` |
| 2026-05-22 | 多步任务触发 `Maximum tool call iterations` | `_max_tool_calls=10` 硬编码 | 改为配置项 `max_tool_calls`（默认 15） |
| 2026-05-22 | 响应内容无渲染，markdown 裸显 | `console.print(f"\n{response}")` | 改用 `console.print(Markdown(response))` |
| 2026-05-22 | 工具调用显示冗长，转义符 `\"` 去不掉 | `json.dumps()` 做显示——JSON 转义是序列化需求不是显示需求，事后 replace 修不完 | 改用 `key=value` 拼接显示，完整 JSON 保留在 `logger.debug` |
| 2026-05-22 | CLI 方向键显现控制字符 | `input()` 未启用 readline | 一行 `import readline` |
| 2026-05-22 | LLM 有 tool_calls 时文字被丢弃 | `assistant_msg` 硬写 `"content": ""` | `assistant_content = response.get("content", "")` |
| 2026-05-22 | 输入/输出/工具日志无视觉层次 | 所有输出混一起 | `console.rule()` 框出 Agent 区 + 回复区 |
| 2026-05-22 | max_tool_calls 超标硬停，不给 LLM 收尾机会 | 直接 return error string，前面 14 次工具调用结果浪费 | 达到上限后注入「请基于已有信息总结」→调 LLM 最后一次（无 tools）→LLM 自己收尾 |
| 2026-05-22 | 工具执行无进度反馈，长命令像卡死 | 调用行打印后静默等待 | `console.status(spinner="dots")` 包裹执行段；完成后打印 `✓ 2.3s` |
| 2026-05-22 | 退出清理分散三处，`os._exit(0)` 跳过 finally | 终端恢复分别写在信号 handler、except、finally | `_on_exit(fn)` / `_run_exit_hooks()` LIFO 模式，所有退出路径统一调用 |
| 2026-05-22 | Static tool call indicator，用户不知工具是否卡死 | 普通 print，执行中无反馈 | `Live()` + spinner sequence `⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏` 原地更新，完成后 `✓ 2.3s` |
| 2026-05-22 | 同批同类工具折叠显示不受认可 | 用户不想要折叠，每步都要可见 | 删除折叠逻辑，全部逐条显示 |
| 2026-05-22 | `Live()` 内颜色丢失 | `Text(f\"...\", style=\"dim\")` 未渲染 Rich markup | 改用 `Text.from_markup(f\"[bright_black]...[/bright_black]\")` |
| 2026-05-22 | Ctrl+C 取消后 Agent 区下底线缺失 | 取消异常处理未输出 `console.rule()` | 补 `console.rule(style=\"dim\")` |
| 2026-05-22 | 工具调用失败直接报错退出，后续对话断掉 | `ToolRegistry.execute()` 无异常兜底，`TypeError` 等直接 propagate → agent 崩溃 | registry.execute() 加 try/except：`TypeError` 返回 `{error, available_params, received_params}` 让 LLM 自愈；通用异常返回 `{error: "类型: 消息"}`；所有错误以工具结果形式喂回 LLM |
| 2026-05-22 | ReadFile 不支持 `offset` 参数 | LLM 传 `offset=` 但 execute() 不接 → `TypeError` | 加 `offset` 参数（1-indexed，切片 `lines[offset-1:]`），同步更新 parameters 定义 |
| 2026-05-22 | max_tool_calls 超标后 LLM 无法申请额外预算 | 硬编码收尾 prompt，LLM 没有「续命」选项 | 新增 `_ask_continuation()`：LLM 评估完成度→回复 `CONTINUE:N` 拓展预算或给最终答案 |
| 2026-05-22 | `_ask_continuation` 大多数未触发 | `while count < max` 循环条件 kill 了底部续命检查 | 改 `while True` + 顶部 guard；重置 `_max_tool_calls` 每轮 |
| 2026-05-22 | LLM 倾向于「做完了停下」而非继续 | 决策 prompt 太中性 | 改任务驱动 prompt：「优先完成任务」「答案不完整就继续」 |
| 2026-05-22 | LLM API 错误（404/401）直接杀对话 | `chat()` 异常 → `raise` 崩溃 | `return f"模型调用失败：{e}"` 不杀对话 |
| 2026-05-22 | Context compressed 后 API 400: "Message has tool role, but no previous assistant message with tool call" | `_truncate()`/`_summarize()` 保留最后 N 条消息时可能切掉带 `tool_calls` 的 assistant，但保留其后 tool 结果 → 孤立 tool 消息被 API 拒绝 | compressor 全面重写：`_sliding()` 滑动窗口 + 锚点保留 + `_extend_to_chain()` 向前追溯补全 tool 链 + `max_input_tokens` 配置驱动（不再是 `messages[-10:]` 硬编码） |
| 2026-05-23 | 续命—LLM 幻觉工具调用绕过预算 | 预算耗尽时仅给 `continue_task` 工具，LLM 从上下文记忆里幻觉出 `read_file`/`bash`，绕过续命 | 改用 `tool_choice="none"` + `tools=[]` 强制纯文字，解析文字中 `CONTINUE N`。详见 `references/continuation-evolution.md` |
| 2026-05-23 | 续命 `role: "system"` 触发 MiniMax 400 | MiniMax 不允许对话中途插入 system 消息 | 回退 `role: "user"` |

## 待修复

| 日期 | 问题 | 描述 | 优先级 |
|------|------|------|--------|
| 2026-05-21 | CLI 等待响应时无法输入 | REPL 同步阻塞在 `agent.run()`。**方案：异步 REPL** | 中 |
| 2026-05-21 | 启动无模型探活 | 模型不存在在用户输入后才报错 | 中 |
| 2026-05-21 | 敏感操作无权限拦截 | bash/file 未接入 SecurityChecker | 高 |
| 2026-05-20 | 工具结果过长撑爆上下文 | 已加 4000 字截断 | 低 |
| 2026-05-22 | cooldown/retry 未走配置层 | 硬编码在 agent.py | 中 |
| 2026-05-22 | 工具调用日志过多刷屏 | 15+ 调用占满终端。**方案：固定高度面板或折叠** | 低 |
| 2026-05-22 | Ctrl+C 提示在输入框上方，打断输入流 | 警告信息打印在当前行上方，input() 被遮。**方案：prompt_toolkit 底部 toolbar，提示在输入框下方，不打断输入。** | 低 |
