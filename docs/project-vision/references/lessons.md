# 开发教训

每次犯错后的反思，避免重蹈覆辙。

---

## 2026-05-21: 不要把 provider 名写进核心代码

**场景**：调试 SCNet 的 429 限流时，在 `llm.py` 的注释和变量名里写了 "SCNet"。

**错误**：`# 关闭 SDK 自动重试（SCNet 不返回 Retry-After，SDK 退避太快）`；重试逻辑硬编码 `2s / 4s`，没有参数化。

**教训**：核心模块不应知道任何 provider 的名字。provider 特定的行为通过配置/参数传入。评论提到具体厂商名 → 说明这个逻辑应该被参数化。

**正确做法**：`LLMClient(retry_delays=(2, 4))`；注释改为通用描述。

---

## 2026-05-21: 修一类 Bug 时要检查同类代码

**场景**：给 `chat()` 加了重试逻辑，但忘了 `chat_stream()` 也有同样的问题。

**教训**：改完一个方法后，搜索同类方法是否有同样的问题。

---

## 2026-05-21: patch 大段代码前先完整读取文件

**场景**：用分页读取看了文件，然后直接 patch，写入验证失败。

**教训**：patch 操作需要完整文件内容验证。如果用了 offset/limit，**必须先 `read_file(path)` 无参读取整个文件**，再执行 patch。

---

## 2026-05-21: "最小修复"不是"只修一个文件"

**场景**：给 `chat()` 加 try/except 时只修了异常处理，没同步给 `chat_stream()`。

**教训**："最小修复"指改动范围最小，不等于只改一个方法。同类代码要一起修。

---

## 2026-05-20: 表面修复只在延迟爆炸

**场景**：之前有人在调用方用 `try/except: pass` 掩盖底层崩溃。

**教训**：修复必须从根因改起，不允许在调用方加 `except: pass` 来掩盖问题。

---

## 2026-05-22: `write_file` 覆盖整个文件 — 局部改动用 `patch`

**场景**：用 `write_file` 只放 `run_repl` 函数体，300 行 main.py 覆盖成 100 行碎片。`git checkout` 救命但丢了所有未提交改动。

**根因**：`write_file` 是全量覆盖，不是替换片段。参数 `content` 是整个文件的新内容。

**教训**：修改已有文件一律用 `patch`。`patch` 失败读完整文件调整 old_string 重试，不退回到 write_file。大规模重写先读完整文件确认内容再写。

---

## 2026-05-22: 超标不是终点 — 让 LLM 自己收尾

**场景**：`max_tool_calls` 撞墙返回 `"Error: Maximum tool call iterations reached"`。用户说"这也太他妈抽象了"。

**修复**：达到上限后注入系统消息「请基于已有信息给出最终回答」→ 再调一次 LLM（不带 tools）→ LLM 自己总结前面获取的信息，自然收尾。

**教训**：只要 LLM 还能用，就不该 agent 代码替它说话。所有限制（token、时间、调用次数）都应该走同一模式：通知 LLM 收尾，它决定怎么结束。

---

## 2026-05-22: 动态反馈 — `console.status(spinner="dots")` 包裹阻塞操作

**场景**：工具执行没有进度反馈，长命令像卡死。用户要动态标志。

**修复**：`with console.status("", spinner="dots"): result = await tool.execute(...)` — 执行期间 dots 动画旋转，完成后印 `✓ 2.3s`。

**教训**：阻塞操作前给视觉反馈，完成后替换为结果。`spinner="dots"` 比静态图标提供"在动"的信息。

---

## 2026-05-22: 信号 handler 做动作不打印

**场景**：按一次 Ctrl+C 出现两条 "操作已取消"。

**根因**：信号 handler 打了一条，`CancelledError` except 又打一条。

**修复**：信号 handler 只负责 `current_task.cancel()`，silent；消息由 except 块统一打。

**教训**：信号 handler 是动作层，不是展示层。

---

## 2026-05-22: `input()` + 简单计数器 — 不手搓输入引擎

**场景**：为"按任意键取消"写了 60 行 `_readline()` 逐字符轮询，WSL 下 select 不稳定，readline 功能全丢。被质疑"有必要吗"。

**教训**：`input()` 是几十年的工业标准——除非你能证明它不够，别替换它。需求"按任意键取消"本质和行缓冲冲突，要么接受要么换 prompt_toolkit——不要手搓。

---

## 2026-05-22: 代码注释只写契约语义 — 变更历史走 commit message + skill docs

**场景**：想顺手加注释。用户阻止："不要随便加注释，补充文档可以"。

**教训**：注释写"为什么是这个值"不写"为什么改这个值"；inline 是最后手段；知识放 skill references/；改完代码同步 skill 文档。

---

## 2026-05-22: key=value 替代 json.dumps 显示参数 — 根因级别的转义消除

**场景**：工具参数 `\"` 转义符一直显示。修过 `\n`→空格、`\uXXXX`→中文，但 `\"` 还在。用户怒："你他妈不知道修根因吗"。

**根因**：`json.dumps()` 的职责是生成合法 JSON——`"` 必须转义为 `\"`。之前的修复是事后清洗，每发现一种转义符补一个 replace，永远修不完。

**修复**：不再用 `json.dumps()` 做显示。改用 `key=value` 拼接。完整 JSON 仍保留在 `logger.debug`。

**教训**：不要在显示层补 replace 列表——修症状不是修根因。显示和序列化是两个不同需求，用同一工具必然冲突。

---

## 2026-05-22: 压缩不当「切了再补」——应从算法层面保证不断链

**场景**：`_truncate()` 用 `messages[-10:]` 硬编码截断，可能切掉带 `tool_calls` 的 assistant 但保留 tool 结果，导致 API 400。第一版修复写 `_fix_tool_chain()` 注入假 `tool_calls` 占位符——用户质疑"是根解吗，可以拓展吗"。

**根因**：截断算法不负责任——只管按条数切，不管消息依赖关系。

**正确做法**：`_extend_to_chain()` 向前追溯，从保留区的孤立 tool 消息往回找到其 assistant 并补入。不是「切了再补假消息」，而是「切之前先保证完整」。

**教训**：占位符/假数据骗 API 是 tactical patch，不是 strategic fix。压缩算法必须从数据结构层面保证链完整性。

---

## 2026-05-22: 锚点锁死第一条 user 是无意义的——锚在当前任务

**场景**：压缩时把第一条 user 消息作为锚点保留。用户指出："如果第一条是'你好'咋办？"

**修正**：锚点从第一条 user 改为最后一条 user——当前任务/问题才是需要保留的上下文。

**教训**：锚点语义要对。"保留第一条消息"的直觉来自"对话起点重要"，但真正重要的是"当前在做什么"。不要让直觉替代业务逻辑。

---

## 2026-05-22: 阈值不用绝对值——用比例

**场景**：`max_input_tokens = 64000` 作为压缩触发条件，写死的。不同模型上下文窗口不同（32K/128K/200K），绝对值要么太小要么太大。

**修正**：`compression_threshold: float = 0.75`——达到 max_input_tokens 的 75% 时触发压缩。配置驱动，自适应所有模型。

**教训**：凡是和模型能力相关的阈值，用比例不用绝对值。比例让同一个配置跨模型复用。

---

## 2026-05-22: LLM 决策注入模式 — 所有预算耗尽场景的统一收尾

**场景**：`max_tool_calls` 超标时，用户要求"让大模型决定是否新增工具调用次数"，且"后面可以复用"。

**实现**：`_ask_continuation(limit_type, current, maximum)`——注入评估 prompt → 调 LLM 无工具 → 解析 `CONTINUE:N` 或接受回答。通用方法，后续重试/搜索/权限拦截均可复用。

**教训**：不要让 agent 代码替 LLM 做决策。任何限制触发时，告诉 LLM 当前状态，让它判断是否继续。这个模式不局限于工具次数——适用于任何"机器检测到边界条件，但 AI 才能判断是否继续"的场景。

---

## 2026-05-22: `while count < max` 杀死了循环底部的续命检查

**场景**：`_ask_continuation()` 放在循环底部，但 `while _tool_calls_count < _max_tool_calls` 在 count 到达 max 后下一轮直接跳出，底部检查永不可达。用户反馈"大多数都没生效"。

**修复**：改为 `while True`，续命检查移到循环顶部——每轮先判断是否超标，超标就调 `_ask_continuation()`。LLM 说继续就扩预算、`continue` 回循环；说够了就返回。

**教训**：循环条件 + 循环体内的边界检查要小心互斥。如果边界检查是"进入下一轮后才能触发"，循环条件必须先放行。`while True` + 顶部 guard 是更安全的结构。不要信任"循环条件会在体内动态失效"的假设。

---

## 2026-05-22: LLM API 错误不应杀对话 — 返回错误让用户修配置

**场景**：`chat()` 返回 404/401 → `raise` → 整个 conversation 崩溃。和之前工具报错一个毛病。

**修复**：`except Exception: return f"模型调用失败：{e}"` 。错误作为 agent 回复展示，对话继续。

**教训**：LLM 调用、工具调用——所有外部操作失败都应该返回结构化信息，不杀对话。用户看到错误能修配置，不需要重新启动。

---

## 2026-05-22: `_max_tool_calls` 跨轮泄漏 — 每轮对话重置预算

**场景**：LLM 把预算从 15 扩展到 20，下一轮对话自动变成 20。用户指出不应该滚雪球。

**修复**：`_agent_loop()` 顶部加 `self._max_tool_calls = self.config.max_tool_calls`。

**教训**：可变状态跨轮使用时必须重置。LLM 扩展的预算是"本轮临时预算"，不是"永久调高上限"。

---

## 2026-05-22: 给 LLM 决策的 prompt 必须是任务驱动的

**场景**：`_ask_continuation` 初始 prompt 太中性——"评估任务完成度"暗示 LLM 应该保守。用户反馈"大多数时候大模型还是不觉得继续"。

**修复**：改 prompt 为"你的任务是完成用户的请求，不是达到调用上限"。"CONTINUE:<N>"前置，停只为"充分完整"才停。

**教训**：LLM 默认倾向于"做了就停"——它不会主动承担任务压力。决策类 prompt 必须明确把"任务完成"放在第一位，"预算节约"放最后。让 LLM 觉得不继续才是失败。

---

## 2026-05-22: 压缩的本质——旧消息 → LLM 摘要，而非截断窗口

场景：压缩器三次迭代。前两版都没真正压缩。

用户反馈：压缩根本没起到压缩的作用。

正确做法：所有旧消息（user + assistant + tool 结果）→ LLM 语义摘要 → 注入为 system 消息。保留 system + 当前任务 + 当前 tool 链 + 摘要。几百条变几句话。

教训：减少消息数量不等于压缩信息。真正的压缩是把信息浓缩——这恰好是 LLM 擅长的事。

---

## 2026-05-23: 不要用对话 prompt 打断 LLM 的工具调用流——给工具让它自己调

场景：续命机制迭代了四版。`_ask_continuation` 用 user prompt 让 LLM 回复 "CONTINUE:N" 文本——LLM 在工具调用模式中被对话问题打断，回复自然语言而非格式，导致续命失效。用户说"明显想要继续申请，但是怎么忽然就结束了？"

教训：LLM 在 function-calling 模式中，有效的交互方式也是 function-calling。不要在它"做事"时丢一个对话问题——给它一个可调用的工具。`continue_task(reason, extra_calls)` 虚工具让 LLM 在调用流中无缝申请，零解析、零格式问题、不切换模式。

通则：凡是需要在 LLM 执行过程中插入决策点的场景，用虚工具而非对话 prompt。LLM 天生会调函数，不会写特定格式的文本。

---

## 2026-05-22: 多配置文件优先级必须显式告知用户

场景：项目级和全局配置各一套，全局不通但用户不知道哪个生效。

修复：启动 banner 加配置来源路径。

教训：多路径配置查找 + 无反馈 = 用户猜不到哪个生效。优先级机制必须可观测。

---

## 2026-05-23: 预算耗尽时 LLM 会幻觉工具调用——用 `tool_choice` API 约束而非剥夺工具

场景：用 `continue_task` 工具做续命。仅给 LLM 这一个工具，它却从历史消息里"回忆"出 `read_file`、`bash` 并直接调用。后续试 `tool_choice="none"` 退化回文字解析——又回到依赖 LLM 格式的老问题。

根因：LLM 的上下文包含大量历史工具调用。prompt 约束不可靠。

最终修复：`tool_choice={"type":"function","function":{"name":"continue_task"}}`——API 层强制 LLM 只能调该工具。不能文字、不能幻觉。这是迭代 5 的终版方案。

教训：当需要限制 LLM 行为时，API 层约束（`tool_choice`）>>> prompt 约束。`"none"` 防所有工具，dict 格式限特定工具，"auto" 自由选择。不要靠 LLM "听话"。

## 2026-05-23: 每次架构设计必须问"不在收录范围内怎么办"

这不是某个具体 bug 的修复——这是适用于所有功能的方法论：

每次设计一个"自动补全""智能推断""默认行为"的功能时，必须先回答：

1. **收录的情况**怎么处理？—自动补、默认值
2. **未收录的情况**怎么处理？—不抛错、警告、要求用户显式提供、建议用 `"custom"` 标注
3. **拓展**要多简单？—加一行/一个配置项就能接入新 case

反面教材：SCNet 硬编码在注释里、base_url 手动填格式错了无提示、provider 只是标签无实际作用。

正面例子：`PROVIDER_REGISTRY`——收录 5 个平台自动补、未收录 warning + 要求显式 base_url、新平台一行注册。

总结：每个「智能」功能必须配一个「我不认识」的 fallback。智能辅助 ≠ 拒绝服务。

---

## 2026-05-23: 解析 LLM 输出——约束 prompt 比写一堆正则更可靠

场景：`_ask_continuation` 的 regex 匹配 LLM 的 CONTINUE 声明。先写了一个正则太死 → 扩展到 5 个正则猜各种格式 → 用户反馈"写得挺龊"。

教训：别写一堆正则猜 LLM 会输出什么格式。在 prompt 里明确约束格式（"第一行必须写：CONTINUE N。例如：CONTINUE 3"），然后一个简单正则解析即可。严格 prompt > 灵活 regex。

---

## 2026-05-23: 收尾——照搬 Hermes 双层 + 承认 provider 天花板

15+ 轮 prompt engineering 全部失败。看 Hermes `conversation_loop.py` 发现双层：

```
Layer 1: _budget_grace_call → 到上限时放行一次，正常带工具
Layer 2: handle_max_iterations → 追加 "已达到最大调用次数。请给出最终回复。" 
         + tool_choice="none"
```

照搬后代码减 45 行。但 MiniMax 不遵守 `tool_choice="none"`——LLM 仍幻觉工具调用。
用泛型 regex `<\w+:tool_call[^>]*>.*?</\w+:tool_call>` 兜底清理。

**结论：收尾效果取决于 provider。** 架构是通解，提示词是通解，
但 provider 的 API 配合度是天花板。不要无限迭代 prompt——
承认边界，做好兜底，换 provider 才能真正解决。

---

## 2026-05-23: 幻觉校验不能依赖工具列表非空——`if tools:` 守卫是根因

场景：预算耗尽时 `tools=[]`，但 LLM 仍幻觉调用工具并被执行。

根因：`if tools:` 守卫——tools 为空时直接跳过整个校验块，LLM 返回的幻觉 tool_calls 被当作合法调用直接执行。

```python
# 旧: if tools:  →  tools=[] 时跳过，幻觉执行
# 新: 始终校验，tools=[] 时 valid_names=set()，全部拦截
valid_names = {t["function"]["name"] for t in tools} if tools else set()
```

教训：`if tools:` 是逻辑漏洞——空列表不是"跳过"的信号，而是"全部拦截"的信号。所有依赖外部列表做校验的逻辑，空值时必须走拦截分支。

---

## 2026-05-23: 续命机制五日迭代归零——最昂贵的教训

**五日的完整路径：**

```
起点：max_tool_calls=15，到头硬停
  ↓ 用户：让 LLM 自己决定要不要继续
第1版 _ask_continuation → 文字解析 "CONTINUE N" → LLM 不跟格式
第2版 continue_task 虚工具 → LLM 幻觉 read_file/bash
第3版 tool_choice="required" + 幻觉校验
  ↓ MiniMax 无视 required
第4版 tool_choice="none" + 文字解析 → LLM 中间过程文字
第5版 tool_choice dict 格式 + 衰减 → MiniMax 不支持
终点：删掉全部，回到 max_tool_calls=50 + 收尾
```

**净投入：** ~15 commits，~200 行增删，0 行留存。

**核心教训：**
> 在 provider 能力边界上建功能不是通解——先确认 API 支持，再设计。
> 做新功能前先看三个成熟 Agent 怎么做。它们都没做续命，大概率不需要。

---

## 2026-05-23: `if tools:` 守卫跳过幻觉校验——条件守卫不等于安全

场景：预算耗尽时 tools=[]，`if tools:` 为 False 跳过校验，LLM 幻觉的工具调用被当作合法调用直接执行。

根因：条件守卫 (`if tools:`) 被用来判断"是否校验"，但语义是"是否有工具"，两者不对等。即便无工具可用，LLM 仍可能返回幻觉调用。

修复：`valid_names = {...} if tools else set()` — 不做条件跳过，始终校验。空工具集 = 全部拦截。

教训：**不要用条件守卫跳过安全校验**。校验永远是兜底，不因外部状态被跳过。

---

## 2026-05-23: LLM 注意力窗口——提示词放消息列表末尾而非头部

**场景：** 收尾 prompt 拼在 system 消息尾部（消息列表位置 0），工具执行 10+ 轮后 system 消息被淹没。LLM 注意力集中在最近几条 tool result 上，根本看不到位置 0 的指令——"已截停"后仍然回复"让我继续查看..."。

**根因：** LLM 的注意力分布不均——对消息列表尾部的最新内容的注意力远高于开头。经过 10+ 轮工具调用后，system 消息的 attention weight 几乎为零。

**修复：** 提示词从 `messages[0]["content"] += ...` 改为 `messages.append({"role": "user", "content": "【系统通知】..."})`。指令在最后一条，LLM 必然看到。

**核心方法 `_inject_stop_prompt`：**
```python
def _inject_stop_prompt(self, messages):
    stop_msg = {"role": "user", "content": "【系统通知】工具已达上限..."}
    return list(messages) + [stop_msg]
```

**教训：** 需要 LLM 立即响应的重要指令永远放消息列表最后一条。system 消息适合持久约束（角色、规则），不适合动态指令（停止、收尾、切换模式）。动态指令放尾部——这是 LLM 注意力最高点。

---

## 2026-05-23 终态：收尾定稿

一天 6 种方案，最终回到最简单的：一条 user 消息。

```python
_wrap_up_messages(messages):
    return messages + [{"role": "user", 
        "content": "已达到最大工具调用次数。请基于已有信息给出最终回复，不要再调用工具。"}]
_wrap_up_call(messages):
    resp = await self.llm.chat(messages, tools=[], tool_choice="none")
    return resp.get("content", "")
```

两条路径（预算到顶 + 批量截停）各一行。tool_choice="none" + 幻觉校验 + regex 三重兜底。

**教训：** Hermes 的 `_budget_grace_call` 依赖 provider 遵守 tool_choice——MiniMax 不遵守，照搬无用。provider 能力边界决定了方案上限。简单 + 兜底 > 复杂 + 依赖特定 API 行为。


---

## 2026-05-26: CLI 输出规范沉淀

以下从 `cli-patterns.md` 合并而来。

### 输出架构

```
> 用户输入
─── Agent ──────────────  ← console.rule(style="dim")
  ⠋ bash (1/15) cmd=...   ← Live spinner, bright_black
  ✓ bash (1/15) cmd=... 2.3s
╭────────────────────────╮
│ 中间文字 / 最终回复      │  ← Panel(Markdown)
╰────────────────────────╯
──────────────────────────  ← console.rule(style="dim")
```

### 工具调用显示

- 格式: key=value 拼接，不用 json.dumps（避免 " 和 \uXXXX 转义）
- 终端宽度动态截断：计算含最终状态 `✓ ... 99.9s` 的完整行，超宽截断
- Live spinner 原地更新：执行中 `⠋` 循环，完成后同位置 `✓ 2.3s`
- 颜色: `Text.from_markup("[bright_black]...[/bright_black]")`
- 无折叠——每条工具调用独立显示

### 终端恢复

- `termios.ECHOCTL` 关闭控制字符回显（禁止 ^C 显示）
- 退出钩子 `_on_exit` / `_run_exit_hooks` LIFO 模式
- `os._exit(0)` 前必须先手动恢复终端

### ANSI prompt

- ``/`​` 包裹 ANSI 码 → readline 正确计宽
- 不用 Rich console.print 做 prompt（光标位置计算错乱）

### 常见坑

- `write_file` 覆盖整文件 → 局部改动用 patch
- Rich status spinner 与 console.print 同一 stdout 会冲突 → 工具日志走 stderr
- stderr/stdout 交叉输出破坏 Rich 光标管理


---

## 2026-05-31: 可观察性的解耦 —— Hooks 事件流而非直接埋点

**场景**：v0.2.0 设计 Observability 时，三种选择摆在面前：
1. agent.py 散落 `metrics.increment("llm_calls")`（直接埋点）
2. Observer 单例直接调用业务方法（双向耦合）
3. 业务代码 emit 事件，Observer/Metrics/Audit 订阅（事件流）

**选择**：第 3 种。HookRegistry 4 个事件（llm.chat/tool.after_execute/tool.error/conversation.turn），Observer 订阅。

**对比**：
- 旧：agent.py 导入 MetricsCollector，6+ 处埋点散落。加新指标改 5+ 文件
- 新：agent.py 只 `await self.hooks.emit(...)`，Observer/Metrics/Audit 各自订阅。改 1 行加新指标

**教训**：
- **解耦的可观察性 = 事件流 + 订阅者**，不是单例 + 全局调用
- 业务代码不感知 Observability 存在，但所有行为都被记录
- 多个订阅者并存（Observer/Metrics/Audit/Tracing）无需改业务代码
- 事件命名要稳定：改动事件名 = 破坏所有订阅者

---

## 2026-05-31: ToolGuard 规则链 —— 默认 ask 不硬拦截

**场景**：v0.2.0 设计敏感命令拦截时，三种选择：
1. 全 deny（rm -rf / 等全拦截）
2. 全 allow（等于没做）
3. 默认 ask（用户决策）+ 用户可加 deny 规则

**选择**：第 3 种。30 条默认规则全 ask（确认后放行），用户可在 `merco.json` 追加 `{"tool":"bash","pattern":"DROP TABLE","action":"deny"}`。

**接入位置**：ToolGuard.check() 在 agent._execute_tool_calls 工具执行前，**不修改任何工具自身**。业务解耦。

**教训**：
- **默认行为要为正常使用留空间**——全 deny 阻断正常开发
- **规则链优先级**——user 规则在链首，可覆盖默认
- **守卫不该侵入工具自身**——hook 模式（agent 层调用）> 装饰器模式（工具层包装）
- **action 三态**：allow（强制放行）/ ask（确认）/ deny（硬拦截）。只有 deny 是终结，allow/ask 都可被后续规则覆盖

---

## 2026-05-31: SessionStore SQLite —— 元数据字段承载跨运行状态

**场景**：Observer 的累计统计（跨运行）需要持久化。两种选择：
1. 单独建一个 `~/.merco/observer.db` 表
2. 复用 `sessions.metadata` JSON 字段

**选择**：第 2 种。`session.metadata["observer"] = observer.snapshot()`，每轮 save 时持久化。

**为什么**：Observer 状态本质属于"这个会话的一部分"。单独建表要处理 observer 与 session 的一对多（一个会话一个 observer，但跨重启 observer 唯一）关系，得不偿失。JSON 字段无 schema 约束，正适合动态 snapshot。

**教训**：
- **元数据 JSON 字段 = 跨域数据的低成本存储**——任何"我需要存点东西但不想建表"的场景都适用
- **Session 状态分层**：messages（高频写）/ metadata（低频写）/ 结构化字段（id/title/created_at）。metadata 字段是"扩展点"
- **未来 Session Fork 复用**：`parent_id` 字段已建好（Phase 5 直接用），Observer snapshot 也跟着 fork 走

---

## 2026-05-31: ProviderInfo dataclass + 向后兼容 `__getitem__`

**场景**：v0.2.0 升级 `PROVIDER_REGISTRY` 从 dict 到 dataclass，dict 风格访问 `PROVIDER_REGISTRY["openai"]["base_url"]` 散落 10+ 处。

**选择**：保留 dataclass + 加 `__getitem__` 向后兼容层。

```python
@dataclass
class ProviderInfo:
    base_url: str
    key_env: str
    def __getitem__(self, key):
        if key == "base_url": return self.base_url
        if key == "key_env": return self.key_env
        raise KeyError(key)
```

**教训**：
- **重构时给"读多写少"的旧 API 加兼容层**比"全量替换"成本低 10 倍
- dataclass 提供类型提示 + IDE 补全，`__getitem__` 让旧调用点零改动
- 向后兼容层宁滥勿缺——你不知道哪个角落的代码还依赖旧 API
- `__getitem__` 只暴露常用字段（base_url/key_env），其他字段强迫走属性访问

---

## 2026-05-31: merco setup 向导 —— ProviderInfo 自动驱动 UI

**场景**：用户首次启动无 API key，需要引导。两种方案：
1. 写死 5 个平台的特殊处理代码
2. 通用向导读 `PROVIDER_REGISTRY` 自动生成

**选择**：第 2 种。`merco setup` 命令读 `PROVIDER_REGISTRY`，5 步流程（选平台→填 key→选 model→确认 base_url→保存）全自动。

**结果**：新增平台只需在 `PROVIDER_REGISTRY` 加一条 `ProviderInfo`，setup 向导 + 自动补全 + base_url 兜底全部自动适配。

**教训**：
- **配置驱动 UI**——任何"枚举型配置项"都该有对应的 UI 自动生成
- **新平台一行注册**——架构好不好，看加新 case 要改几行
- **fallback 必须有**——未收录的 provider 必须有清晰的"我不认识这个"路径（warning + 要求显式 base_url）
- **5 步流程**——超过 5 步用户会中途放弃；少于 3 步说明信息量不够

---

## 2026-05-31: Token fallback —— Provider 不返回 usage 时的兜底

**场景**：MiniMax 流式 API 不返回 `usage` 字段，OpenAI/Anthropic 缓存字段名不同（`cached_tokens` vs `cache_read_tokens`）。

**解决**：
1. `_extract_usage` 统一字段映射：`cached_tokens or cache_read_tokens` 都采集
2. `total_tokens` 优先 `last_actual_tokens`，零时回退 `est_tk(content+reasoning)`
3. 进度条永不显示 0

**教训**：
- **多 provider 兼容 = 字段映射层**——别在调用方写 `if provider == "openai"`，统一抽象 `_extract_usage`
- **进度条永不为 0**——估算出错比 0 显示好。0 让用户以为 agent 没在工作
- **缓存命中率是有用指标**——各 provider 字段不同，但语义一致，统一抽象后 Observer 自动统计

---

## 2026-05-31: SkillViewTool 动态 describe() —— 工具元数据按需生成

**场景**：技能列表会变化（新增/删除/改描述），但 system prompt 是静态的。两种方案：
1. 启动时拼 system prompt（含技能列表）
2. 工具 describe() 动态生成

**选择**：第 2 种。`SkillViewTool.describe(context)` 在 tool definition 调用时拼接当前可用技能列表。

**附加设计**：
- `check()` 方法：有技能才显示工具（无技能时不暴露 `skill_view`）
- `set_skill_registry()` 注入：避免循环导入

**教训**：
- **静态 system prompt + 动态工具元数据**——技能列表在 tool description 而非 system prompt，更新零改动
- **check() 控制可见性**——无依赖的工具不暴露，避免 LLM 调空工具
- **注入而非导入**——循环依赖的通解。`set_registry()` 在 Agent 构造时调用，模块 import 阶段无依赖

---

## 2026-05-31: 集成测试用 MockLLMClient —— 测试金字塔顶端

**场景**：v0.2.0 需要测试 Agent 端到端流程（对话/工具/会话/guard/压缩）。真实 LLM 调用：
- 慢（每次 5+ 秒）
- 贵（CI 跑测试 1000 次烧钱）
- 不确定（同样输入不同响应）

**解决**：`tests/conftest.py` 提供 `MockLLMClient` fixture：
```python
class MockLLMClient:
    def __init__(self, responses: list[dict]):
        self.responses = responses
        self.call_count = 0
    async def chat(self, *args, **kwargs):
        resp = self.responses[self.call_count]
        self.call_count += 1
        return resp
```

**测试速度**：2 秒全过 10+ 集成测试。CI 友好。

**教训**：
- **集成测试 mock LLM，单元测试 mock 一切**——CI 不依赖外部服务
- **测试用例是 LLM 响应序列**——可读性 > 灵活性。预设 `responses=[...]` 列出每轮的 LLM 输出
- **MockLLMClient 不验证响应格式**——格式错就当 LLM 出错走恢复路径，与真实行为一致
- **测试金字塔**：单元（多、快）+ 集成（中、MockLLM）+ E2E（少、真实 LLM，可选）

---

## 2026-05-31: openai import 延迟加载 —— 测试环境解耦

**场景**：`merco/core/llm.py` 顶部 `from openai import AsyncOpenAI`。测试环境 conftest.py 不安装 openai，整个 agent 模块 import 失败。

**解决**：openai import 延迟到 `LLMClient.__init__`：
```python
class LLMClient:
    def __init__(self, ...):
        import openai  # 延迟到实例化
        self.client = openai.AsyncOpenAI(...)
```

**教训**：
- **顶层 import 是隐式强依赖**——任何缺失导致整个模块崩
- **延迟 import = 可选依赖**——只在实际使用时检查依赖
- **测试环境依赖最小化**——conftest 只 import 必要模块，缺失的留给延迟 import 处理
- **架构层观察**：llm.py 是 core 模块，被测试大量 import。第三方 SDK 应放在实例化阶段

---

## 2026-05-31: Skill 文档与代码同步纪律 —— 三个副本必须对齐

**场景**：v0.2.0 发布后，发现三个 skill 副本严重不一致：
- `docs/project-vision/` (源) — 已更新到 2026-05-28
- `.merco/skills/` — 内容更新但描述了未实现功能
- `.opencode/skills/` — 停留在 2026-05-20（OpenMercury 命名）
- `.reasonix/skills/` — 停留在 2026-05-22

**根因**：每次大提交未同步副本。"源 → 副本"单向同步纪律缺失。

**教训**：
- **"提交后同步"是 hard rule**——和"提交前跑测试"同等重要
- **多副本场景必须以源为唯一真相**——副本只允许来自源的同步
- **副本中的"未来功能描述"必须明确标记 Phase**——避免用户误以为已实现
- **grep 验证是底线**——文档声称的功能，grep 代码必须能找到对应实现

---

## 2026-05-31: 命名变更 OpenMercury → Mercury Code (merco) — 一次大扫除

**场景**：项目名 OpenMercury 改为 Mercury Code (merco) 更简洁，5 个文件 mtime 显著不同（`docs/SKILL.md` 已改、`.opencode/SKILL.md` 没改）。

**教训**：
- **项目改名不是只改 README**——所有外部引用、skill 副本、文档入口、配置文件、commit message 都要扫一遍
- **`grep -r "OpenMercury"` 是改名后的第一步**——机械但有效
- **多 skill 副本场景下改名成本倍增**——副本越多越容易漏
- **rename 提交 + docs 同步应原子化**——不要拆分到不同 commit
