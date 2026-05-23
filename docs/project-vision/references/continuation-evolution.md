# 续命机制演化记录

## 背景

OpenMercury 的 `max_tool_calls` 默认 15，LLM 在复杂任务中容易超标。需要一种机制让 LLM 在预算耗尽时决定继续或收尾。

## 尝试过的方案

### 方案 1: `_ask_continuation()` — user prompt 文字格式

```
预算耗尽 → 注入评估 prompt（role=user）
→ LLM 无工具纯思考
→ 回复 "CONTINUE:N" → 拓展预算
→ 否则 → 最终回答
```

**失败原因：**
- LLM 不遵守 "CONTINUE:N" 格式，回复自然语言（"我需要继续查…"）
- `role: "system"` 在 MiniMax 上报 400（中间不允许 system 消息）
- `role: "user"` 服从度低

### 方案 2: `continue_task` 虚工具 + `tool_choice="required"`

```
预算耗尽 → tools=[continue_task], tool_choice="required"
→ LLM 被强制调用 continue_task(reason, extra_calls)
→ 系统拦截 → 拓展预算
```

**失败原因：**
- MiniMax API 不遵循 `tool_choice="required"` 约束
- LLM 仍幻觉出 read_file/bash 工具调用（从上下文记忆中）
- `tool_choice` dict 格式 `{"type":"function","function":{"name":"x"}}` 在 MiniMax 上返回 `finish=stop`（纯文字）

### 方案 3: `tool_choice="none"` + 文字解析 + 幻觉校验

```
预算耗尽 → tools=[], tool_choice="none"
→ LLM 只能回文字
→ 正则搜 CONTINUE N
→ 幻觉校验层过滤非法 tool_calls
```

**失败原因：**
- LLM 文字回答是中间过程评论（"让我继续查…"），非 `CONTINUE N` 格式
- 幻觉校验层过滤后，剩余文字仍不是完整答案
- 即使解析到 CONTINUE，概率很低

### 方案 4: 衰减续命负担

```
第1次继续: +15
第2次: +10
第3次: +5
第4次: +3
第5次+: +1
```

目的一：LLM 自然选择高效完成。目的二：软压力替代硬上限。

**失败原因：**
- 续命机制本身不可靠（方案 2/3 的问题），衰减只是锦上添花

## 最终方案：删除续命，简单预算+收尾

```
max_tool_calls: 50（从 15 增大）
预算耗尽 → tool_choice="none" + "请基于已有信息给出完整结论"
→ LLM 给出最终回答
```

**设计依据：**
- Hermes Agent: `max_turns=90`，到头自然结束
- Claude Code: 无工具上限，token 预算自然约束
- Codex CLI: `max_iterations=50`，硬限
- 三者均无续命机制

**保留的机制：**
- 自动扩容：批次不会出现 16/15 显示
- 幻觉校验：过滤不在 tools 列表的调用
- 硬上限：`max_tool_calls × 3`（当前 150）

## 教训

**核心教训：当一个"通用"方案需要 provider 特定 API 行为配合时，它不是通解。退回 API 最基础能力（tool_choice=none、tools=[]）才是通解。**

具体：
- `tool_choice="required"` 是 OpenAI 标准，但不是所有 provider 都完整实现
- `tool_choice` dict 格式是标准扩展，更窄的兼容性
- `role: "system"` 中间注入在某些 API 上报 400
- 幻觉工具调用是真问题——不依赖 provider 的校验层是必要的
- LLM 的文字格式服从度不可靠，不应作为关键路径

## 诊断方法

调试 MiniMax tool_choice 行为：
1. 发送 `tool_choice={"type":"function","function":{"name":"x"}}` → 观察 `finish=stop` 还是 `finish=tool_calls`
2. 发送 `tool_choice="required"` + `tools=[single_tool]` → 观察是否返回非列表工具
3. 在 response 后加校验层比对 tools 列表
