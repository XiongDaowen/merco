# API 错误可见性与重试反馈修复

日期：2026-07-06
状态：待审核

## 问题

对话期间（thinking 阶段或 content 输出阶段），API 出错后用户看不到任何错误提示——
流式 Live 面板消失后终端是空白的（"空窗口"）。重试是静默的（`asyncio.sleep` 期间终端
无任何反馈，用户以为卡死）。不可重试错误（如 401）也静默返回字符串，REPL 在流式模式下
跳过打印，导致错误信息完全丢失。

## 目标

1. **杜绝空窗口**：API 出错时必有红色错误 Panel 显示，面板包含错误分类、用户提示、脱敏细节
2. **重试有反馈**：恢复管线重试时显示黄色一行提示，等待 >1s 时显示 spinner，不留成功痕迹
3. **最终失败有红 Panel**：重试耗尽或恢复管线无法处理时，红色 Panel 作为最终响应
4. **不污染对话历史**：错误消息不写入 session/context，下轮 LLM 看不到错误
5. **流式/非流式统一体验**：不因 `streaming` 开关影响错误展示质量
6. **不遗漏重试机会**：所有 API 异常都进入恢复管线重试；确定性错误（401/403/404）只快速重试 1 次

## 非目标

- 不做错误事件的 hook 化/插件化（YAGNI，现有直接 `console.print` 风格够用）
- 不把错误持久化到 session history（用户 `/history` 看不到错误记录）
- 不新增"切换备选模型"的恢复策略（未来再加）
- 不重构 REPL 其他部分，只改错误响应的渲染分支

## 架构

### 新模块：`merco/core/llm/error_ui.py`

职责集中：只管"错误长什么样"，不管"什么时候显示"。零副作用（不写日志、不 import openai）。

```
ErrorInfo(label: str, hint: str, exc: Exception)     # dataclass

classify_error(exc) -> ErrorInfo                     # duck typing 分类，不 import openai
sanitize_message(exc, max_len=300) -> str            # 脱敏 + 截断
build_error_panel(info: ErrorInfo) -> Panel          # 红 Panel（label + hint + 脱敏细节）
build_retry_line(info, attempt, max, actions) -> str # 黄字一行 "↻ ..."
retry_spinner(label, seconds, console) -> async ctx  # 等待期间的 spinner（transient）
error_message(info: ErrorInfo) -> str                # 以 "❌ " 开头的 Rich markup 字符串
```

红 Panel 不包含已输出的 reasoning/content——已输出内容由保留的 content_panel 或
transient 静态副本显示，错误面板只做错误提示，职责单一。

### 改动点汇总

| 文件 | 改动 |
|---|---|
| `merco/core/llm/error_ui.py` | **新增**。集中错误 UI 逻辑 |
| `merco/core/llm/errors.py` | `llm_error()` 改为对 `error_ui.error_message()` 的薄包装；删除 `_is_retryable_llm_error`（逻辑下沉到 WaitRecovery）；删除之前未经设计确认加的 `_classify_error` |
| `merco/core/recovery/wait.py` | 不再依赖 `_is_retryable`；按错误类型差异化等待：429/5xx/网络 3→6→12s 退避（cap 30s），413 返回 False（让压缩处理），401/403/404 短等 1s 且只 1 次，其他 2→4→8s 退避 |
| `merco/context/recovery.py` | 413/上下文过长关键词强制触发压缩（即使上下文不大）；其他保持原样 |
| `merco/core/agent.py` | StreamingProvider：加 `except Exception` 用红 Panel 替换 thinking 面板，finally 在 transient/空 bufs 时打静态红 Panel，设置 `agent._error_displayed_in_stream=True`，异常上抛；agent loop except 块用 error_ui 渲染重试提示+spinner，最终失败返回 `error_message(info)`；删除之前散落在 agent.py 里的错误渲染逻辑（`_show_error_in_panel` 闭包、重复的 Panel 打印）；`_wrap_up_call` 失败时返回 `error_message()`，不打 Panel（REPL 统一打） |
| `cli/main.py` | REPL 检测 `response.startswith("❌")` 时，若 `not agent._error_displayed_in_stream` 则用 `Text.from_markup` 打红 Panel；正常响应逻辑不变 |
| `merco/core/agent.py`（Agent.__init__/run/reset） | 初始化 `self._error_displayed_in_stream = False`；每轮 `run()` 开始重置；`reset()` 重置 |

### 数据流

```
用户输入 → agent.run() → _agent_loop()
                              ↓
                 _provider.get_response()  ← StreamingProvider / NonStreamingProvider
                              ↓
                    API 异常 → Provider 捕获
                              ↓
                    ├─ StreamingProvider: 红 Panel 替换 thinking 面板 → finally 必要时打静态副本
                    │                   → 设置 _error_displayed_in_stream=True → raise
                    └─ NonStreamingProvider: 异常直接 raise（无 UI 逻辑）
                              ↓
                 agent loop except 块
                              ↓
                    ├─ 重试次数 > 3 → 返回 error_message(info)
                    ├─ recovery_pipeline.attempt(ctx)
                    │     ├─ WaitRecovery 按错误类型决定等多久
                    │     └─ ContextCompressRecovery 判断是否压缩
                    │           ↓ 失败 → 返回 error_message(info)
                    │           ↓ 成功
                    └─ 打黄字一行 + 可选 spinner → 执行等待/压缩/切模型 → continue 重试
                              ↓
                 REPL 收到响应字符串
                    ├─ startswith("❌") 且 未在流式层显示 → 红 Panel
                    ├─ startswith("❌") 且 已在流式层显示 → 跳过（避免重复）
                    └─ 正常响应 → 按原逻辑 Panel(Markdown) 或跳过（streaming 已显示）
```

### 错误类型差异化策略

| 类型 | 触发条件 | WaitRecovery 行为 | 提示 |
|---|---|---|---|
| 429 限流 | status=429 或关键词 | 3→6→12s 退避 | "请求限流" |
| 5xx 服务端 | 500-599 | 3→6→12s 退避 | "服务端错误 (xxx)" |
| 网络/超时 | ConnectionError/Timeout/关键词 | 3→6→12s 退避 | "连接错误"/"请求超时" |
| 413 过长 | status=413 或上下文关键词 | WaitRecovery 返回 False，让 ContextCompressRecovery 处理；ContextCompressRecovery 在返回 True 时设置 `ctx.extra_wait = max(ctx.extra_wait, 0.5)`，给 API 一个喘息 | "请求过长" |
| 401/403/404 确定性 | 对应 status 或关键词 | **短等 1s 仅 1 次**，第二次起返回 False | "认证失败"/"权限不足"/"模型不存在" |
| 其他 4xx | status 4xx 未命中上述 | 2→4→8s 退避 | "API 错误 (xxx)" |
| 其他未知 | 兜底 | 2→4→8s 退避 | 异常类名作为 label |

WaitRecovery 短等判定通过 `ctx.attempt_count`（已尝试次数）判断：对 401/403/404，
`attempt_count >= 1` 就返回 False（即总共只等 1 次、快速重试 1 次，然后放弃）。

### 重试反馈视觉规范

- **重试行**（黄色，一行）：`↻ API 请求限流（第 1/3 次）— 等待 3s + 压缩上下文…`
- **等待 spinner**（黄色，transient Live，>1s 才显示）：`⠋ 等待 2.3s 冷却中…`
- **压缩**：沿用现有 `[dim]→ Context compressed (LLM summarized)[/dim]` 提示
- **切模型**：`[dim]  → 模型切换为 xxx[/dim]`
- **最终失败**（红色 Panel，持久）：
  ```
  ┌─ ⚠ API 错误 ──────────────────┐
  │ ❌ 服务端错误 (502)           │
  │ API 服务器返回 502，稍后重试… │
  │                               │
  │ <脱敏后的错误详情>            │
  └───────────────────────────────┘
  ```

### 不做的事

- 错误不写入 session/context（不污染对话历史）
- 流式过程中已收到的 content 面板保留，但错误面板**替换**（不追加）thinking 面板
- 非 transient 模式下 StreamingProvider 已经在 Live 里显示了红 Panel，REPL 通过
  `_error_displayed_in_stream` 标记避免重复打
- 成功重试后 spinner 和重试行留在上面（自然上滚），不主动清除（spinner 自身是 transient 会消失）

## 测试计划

1. **单元测试 error_ui.py**：
   - `classify_error` 对各种模拟异常（带 status_code 属性的 mock、普通 Exception、AuthenticationError 等）返回正确的 label/hint
   - `sanitize_message` 脱敏 api_key、截断超长
   - `build_error_panel` 返回 Panel，renderable 包含 label/hint/脱敏消息
   - `build_retry_line` 格式正确
   - `error_message` 以 "❌ " 开头

2. **单元测试 WaitRecovery**：
   - 对 mock 的 500 错误，第一次 attempt 返回 True 且 extra_wait=3s
   - 对 mock 的 401 错误，第一次返回 True 且 extra_wait=1s，第二次 attempt_count=1 返回 False
   - 对 mock 的 413 错误返回 False
   - 退避翻倍（3→6→12，cap 30）

3. **集成测试 StreamingProvider 错误路径**：
   - mock `llm.chat_stream` 立即抛 APIStatusError(502)
   - 断言 provider 抛异常前调用了 console.print 或显示了红 Panel
   - 断言 `agent._error_displayed_in_stream` 被设为 True
   - 断言 reasoning/content bufs 为空时仍然有错误 Panel 显示（无空窗口）

4. **集成测试 agent loop 重试**：
   - mock llm 前两次抛 429，第三次返回正常响应
   - 断言 retry_line 被打印两次
   - 断言最终得到正常响应（不返回错误字符串）

5. **集成测试最终失败**：
   - mock llm 持续抛 500
   - 断言重试 3 次后返回以 "❌ " 开头的错误字符串
   - 断言错误字符串不含敏感信息

6. **集成测试 REPL 层**：
   - 模拟 agent.run 返回 "❌ ..." 且 `_error_displayed_in_stream=True` → 不重复打 Panel
   - 模拟 agent.run 返回 "❌ ..." 且 `_error_displayed_in_stream=False` → 打红 Panel
   - 模拟正常响应 → 走原逻辑

## 回滚策略

所有改动集中在 6 个文件，其中 1 个新增。若需回滚，`git revert` 对应 commit 即可，
不涉及数据迁移或配置变更。
