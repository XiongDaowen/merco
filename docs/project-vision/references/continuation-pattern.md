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

---

## 演化历史

### 背景

OpenMercury 的 `max_tool_calls` 默认 15，LLM 在复杂任务中容易超标。需要一种机制让 LLM 在预算耗尽时决定继续或收尾。

### 方案 1: `_ask_continuation()` — user prompt 文字格式

预算耗尽 → 注入评估 prompt（role=user）→ LLM 无工具纯思考 → 回复 "CONTINUE:N" → 拓展预算 → 否则 → 最终回答

**失败原因：** LLM 不遵守 "CONTINUE:N" 格式；`role: "system"` 在 MiniMax 上报 400；`role: "user"` 服从度低。

### 方案 2: `continue_task` 虚工具 + `tool_choice="required"`

预算耗尽 → tools=[continue_task], tool_choice="required" → LLM 被强制调用 → 系统拦截 → 拓展预算

**失败原因：** MiniMax API 不遵循 `tool_choice="required"`；LLM 仍幻觉出 read_file/bash 调用；dict 格式在 MiniMax 上返回 `finish=stop`。

### 方案 3: `tool_choice="none"` + 文字解析 + 幻觉校验

预算耗尽 → tools=[], tool_choice="none" → LLM 只能回文字 → 正则搜 CONTINUE N → 幻觉校验层过滤非法 tool_calls

**失败原因：** LLM 回复中间过程评论而非 CONTINUE 格式；幻觉得不到过滤。

### 方案 4: 衰减续命负担

第 1 次继续 +15，第 2 次 +10，第 3 次 +5，第 4 次 +3，第 5 次起 +1

**失败原因：** 续命机制本身不可靠（方案 2/3 的问题），衰减只是锦上添花。

### 方案 5: Grace Call（已废弃）

参考 Hermes Agent 的 `_budget_grace_call` — 到上限时多给一次正常调用（有工具）。LLM 如果在最后一次自觉给文字回应则自然收尾。

**失败原因：** MiniMax 不配合，LLM 继续调工具，循环退出后没收尾文本。

**教训：** Grace call 依赖 LLM 配合——MiniMax 不给。不要在外面套一层，回来还是得自己加 prompt。该方案已从代码中完全删除。

### 最终方案：删除续命，简单预算+收尾

```
max_tool_calls: 50（从 15 增大）
预算耗尽 → tool_choice="none" + "请基于已有信息给出完整结论"
→ LLM 给出最终回答
```

**设计依据：** Hermes Agent（max_turns=90，到头自然结束）、Claude Code（无工具上限，token 预算自然约束）、Codex CLI（max_iterations=50，硬限）——三者均无续命机制。

**保留的机制：** 自动扩容（批次不会 16/15）、幻觉校验（过滤非法调用）、硬上限（max_tool_calls × 3，当前 150）。

### 核心教训

**当一个"通用"方案需要 provider 特定 API 行为配合时，它不是通解。退回 API 最基础能力才是通解。**

- `tool_choice="required"` 是 OpenAI 标准，但不是所有 provider 都完整实现
- `role: "system"` 中间注入在某些 API 上报 400
- LLM 的文字格式服从度不可靠，不应作为关键路径
