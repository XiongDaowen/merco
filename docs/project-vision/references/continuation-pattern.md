# LLM 决策注入模式 (_ask_continuation)

## 问题

任何预算/限制耗尽时（工具调用次数、token、重试次数、时间），agent 代码不应替 LLM 决定"该停了"——应由 LLM 自己评估是否有足够信息完成任务。

## 模式

```python
should_continue, extra_budget, content = await self._ask_continuation(
    limit_type="工具调用次数",
    current=15,
    maximum=15,
)

if should_continue:
    self._max_tool_calls += extra_budget
    continue  # 回到循环
else:
    return content  # LLM 的最终回答
```

## 方法签名

```python
async def _ask_continuation(
    self, limit_type: str, current: int, maximum: int
) -> tuple[bool, int, str]:
```

返回 `(should_continue, extra_budget, content)`:
- `should_continue=True` → content 是理由文字，agent 拓展预算后继续
- `should_continue=False` → content 是最终回答

## 注入的 Prompt 模板（当前版本）

```
你已达到 {limit_type} 限制（{current}/{maximum}）。

你的任务是完成用户的请求。如实评估：

如果还需继续，回复格式（第一行）：CONTINUE N
（N 是数字，表示还需几次。例如：CONTINUE 3）
如果已充分完成，直接给出最终回答。

优先完成任务。你的回应：
```

注意：
- 用 `role: "user"`，不用 `role: "system"` — MiniMax/部分 API 拒绝中间 system 消息
- 提示词提供明确格式示例（`CONTINUE 3`），不要只描述"回复格式"
- 首行优先匹配，垮到全文 fallback（LLM 可能把 CONTINUE 写在第二行）

## 适用场景

| 触发点 | limit_type | 示例 |
|--------|-----------|------|
| 工具调用次数到上限 | "工具调用次数" | CONTINUE:5 |
| 搜索结果连续为空 | "搜索重试次数" | 直接给最终回答 |
| 权限拦截多次 | "权限拦截" | CONTINUE:2 → 换方案 |
| Token 预算快耗尽 | "Token预算" | 直接收尾 |
| 时间限制快到了 | "时间限制" | 评估能不能快速完成 |

## 设计原则

1. **LLM 是决策者** — agent 代码只检测边界条件，不替 LLM 做判断
2. **严格格式 > 灵活正则** — 让 LLM 输出固定格式（`CONTINUE N`），比写一堆正则猜格式可靠
3. **通用可复用** — 同一个方法，不同的 `limit_type` 字符串
4. **失败兜底** — LLM 调用失败时返回 `False, 0, error_msg`
5. **cap 上限** — extra_budget 最大 10，防止无限循环
6. **每轮重置** — `_max_tool_calls` 在 `_agent_loop()` 顶部重置为 `config.max_tool_calls`，防止跨轮泄漏

## 循环结构陷阱

```python
# ❌ 错误 — while 条件杀死续命
while self._tool_calls_count < self._max_tool_calls:
    execute_tools()
    if self._tool_calls_count >= self._max_tool_calls:
        _ask_continuation()  # ← 不可达！count 到 max 时 while 直接退出

# ✅ 正确 — while True + 顶部 guard
while True:
    if self._tool_calls_count >= self._max_tool_calls:
        should_continue, extra, content = await self._ask_continuation(...)
        if should_continue:
            self._max_tool_calls += extra
            continue
        return content
    call_llm()
    execute_tools()
```

## 调试清单

续命不生效时的排查顺序：
1. 检查 LLM 是否真的输出了 `CONTINUE N` 格式 — 开 `--debug` 看日志
2. `self._max_tool_calls` 是否真的被扩展了 — 在 `_ask_continuation` 返回后加日志
3. 循环是否在续命前退出了 — `while count < max` 的陷阱
4. API 是否拒绝中间 system 消息 — 换 `role: "user"`
