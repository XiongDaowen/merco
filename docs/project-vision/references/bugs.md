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
| 2026-05-21 | 请求频发触发网关限流 | agent loop 无请求间隔，工具执行后立刻发下一请求 | 新增 `cooldown` 参数（默认 1s） |
| 2026-05-21 | 注释/代码里写了 SCNet | 核心模块不应知道 provider 名 | 全部清除，参数化 `retry_delays`/`cooldown` |

## 待修复

| 日期 | 问题 | 描述 | 优先级 |
|------|------|------|--------|
| 2026-05-21 | CLI 方向键显示 `^[[C`/`^[[D` | `input()` 未启用 readline，按左右键输出控制字符而非移动光标 | 中 |
| 2026-05-21 | CLI 等待响应时无法输入 | REPL 同步阻塞在 `agent.run()`，结果出来前输入框不出现，无法连续发消息。**方案：异步 REPL，正常输入排队不打断，Ctrl+C 取消当前任务切新消息。** | 中 |
| 2026-05-21 | 启动无模型探活 | 模型不存在/认证失败在用户输入后才报错，应先 ping 验证 | 中 |
| 2026-05-21 | 敏感操作无权限拦截 | bash/file 工具未接入 `SecurityChecker`/`PermissionManager`，可执行 `rm -rf /` | 高 |
| 2026-05-20 | 工具结果过长撑爆上下文 | 已加 4000 字截断，但 `dir`/`cat` 等仍可能触发 API 拒绝 | 低 |
