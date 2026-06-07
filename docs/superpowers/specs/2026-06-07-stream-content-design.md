# 流式 Content 输出设计

**日期**: 2026-06-07  
**状态**: 已批准  
**作者**: Hermes Agent + 用户协作

## 背景

### 现状问题

1. **stream_content 配置项未实现**
   - `config.py L136` 定义了 `stream_content: bool = False`
   - `StreamingProvider.get_response()` 没有使用这个配置
   - content 累积到 `content_buf`，最终一次性返回给 REPL

2. **Thinking 卡顿**
   - `live.update()` 只在收到 reasoning chunk 时调用（`agent.py L196`）
   - 如果 API 返回 reasoning 的速度慢（比如每 5 秒一个 chunk），Live 面板看起来"卡住"

3. **Thinking 闪现**
   - `transient=True`（`agent.py L150`）→ `live.stop()` 时清除面板
   - thinking 结束后，面板立即消失
   - content 在 `cli/main.py L460` 一次性打印，造成"thinking 消失 → content 突然闪现"

### 用户需求

- `stream_content=True` 时，content chunk 实时打印到终端
- Thinking 框保留（不消失）
- Content 也带框（复用 thinking 的 Live + Panel 逻辑）
- Thinking 不卡顿（即使 API 返回慢，Live 也持续刷新）

## 设计目标

1. **实现 stream_content 流式输出**
   - content chunk 实时打印，不用 Panel 包裹（纯文本流式）
   - 最终返回完整 content 给 `_agent_loop`（保持现有逻辑）
   - `cli/main.py` 检查是否已经流式打印过，避免重复打印

2. **修复 thinking 卡顿**
   - 用 `asyncio.create_task` 启动定时刷新任务（每 0.5 秒）
   - 即使没有新 reasoning chunk，也更新 Live（显示"思考中..."或最新内容）
   - thinking 结束后，取消定时任务

3. **Thinking 框保留**
   - `transient=False`（thinking 框结束后不清除）
   - thinking 框自然滚动到上面

4. **Content 也带框**
   - 创建第二个 `Live` + `Panel`（标题"💬 Response"）
   - content chunk 到达时，`live.update(Panel(content_buf))`
   - content 打印完毕后，`live.stop()`（`transient=False` 保留框）

## 详细设计

### 1. 配置层

**修改文件**: `merco/core/config.py`

```python
# 现状
streaming: bool = False
stream_thinking: bool = True
stream_content: bool = False
stream_render_interval: float = 0.05

# 修改后
streaming: bool = True
stream_thinking: bool = True
stream_content: bool = True              # 改为 True（默认流式）
stream_thinking_transient: bool = False  # 新增（默认保留 thinking 框）
stream_render_interval: float = 0.05
```

**配置文件兼容**:
- 如果用户的 `~/.config/merco/config.json` 没有这些字段，使用默认值
- 如果用户显式设置了 `stream_content: false`，尊重用户配置

### 2. StreamingProvider 改动

**修改文件**: `merco/core/agent.py`

#### 2.1 Thinking 卡顿修复

```python
# 现状
live.update(_build_reasoning_panel(reasoning_buf))  # 只在收到 reasoning chunk 时调用

# 修改后
async def _refresh_thinking():
    """定时刷新 thinking 面板，防止卡顿"""
    while True:
        await asyncio.sleep(0.5)
        if live:
            live.update(_build_reasoning_panel(reasoning_buf))

refresh_task = asyncio.create_task(_refresh_thinking())
try:
    async for chunk in stream:
        # ... 处理 chunk ...
        if r:
            reasoning_buf += r
            if stream_think:
                live.update(_build_reasoning_panel(reasoning_buf))
finally:
    refresh_task.cancel()
    try:
        await refresh_task
    except asyncio.CancelledError:
        pass
```

#### 2.2 Content 流式输出

```python
# 现状
content_buf += chunk.get("content", "")
# 不流式显示

# 修改后
content_buf += chunk.get("content", "")
if stream_content and content_live:
    content_live.update(_build_content_panel(content_buf))
```

#### 2.3 Transient 配置

```python
# 现状
live = Live(panel, console=console, refresh_per_second=10, transient=True)

# 修改后
transient = agent.config.stream_thinking_transient
live = Live(panel, console=console, refresh_per_second=10, transient=transient)
```

### 3. CLI 层改动

**修改文件**: `cli/main.py`

```python
# 现状
response = await agent.run(user_input)
console.print(Panel(Markdown(response), border_style="dim"))
console.rule(style="dim")

# 修改后
response = await agent.run(user_input)
if not agent.config.stream_content:
    # 如果没有流式打印，一次性打印
    console.print(Panel(Markdown(response), border_style="dim"))
console.rule(style="dim")
```

### 4. 错误处理与边界情况

#### 场景 1：stream_content=True 但 API 返回空 content

- 现状：`_agent_loop` 会走空回复重试逻辑
- 修改后：如果 `StreamingProvider` 流式打印了 content，但 content 为空，REPL 层不打印（避免重复）
- 空回复重试逻辑不变（在 `_agent_loop` 里）

#### 场景 2：stream_content=True 但有 tool_calls

- 现状：有 tool_calls 时，content 通常为空或很短（"让我调用工具..."）
- 修改后：如果 `StreamingProvider` 流式打印了 content，但后续有 tool_calls，REPL 层不打印（避免重复）
- tool_calls 的显示逻辑不变（在 `_agent_loop` 里）

#### 场景 3：用户 Ctrl+C 取消流式输出

- 现状：`CancelledError` 处理逻辑在 `_agent_loop` 里
- 修改后：如果 `StreamingProvider` 正在流式打印 content，用户取消，Live 会正常停止（`finally` 块）
- 部分 content 会保留在屏幕上（`transient=False`）

#### 场景 4：thinking 和 content 同时流式

- 现状：API 先返回 reasoning chunks，再返回 content chunks
- 修改后：thinking 结束后，创建第二个 Live 用于 content
- 两个 Live 不会同时运行（thinking 结束后才创建 content Live）

## 测试与验证

### 测试场景

1. `stream_content=True` + `stream_thinking=True` — thinking 框保留 + content 流式带框
2. `stream_content=True` + `stream_thinking=False` — thinking 一次性显示 + content 流式带框
3. `stream_content=False` + `stream_thinking=True` — thinking 框保留 + content 一次性显示
4. `stream_content=False` + `stream_thinking=False` — 现状行为（向后兼容）
5. 用户 Ctrl+C 取消流式输出 — Live 正常停止，部分 content 保留
6. 空 content + tool_calls — 不重复打印

### 验证方法

- 手动测试：启动 merco，输入问题，观察输出
- 检查 thinking 框是否保留
- 检查 content 是否流式带框
- 检查 Ctrl+C 取消是否正常

## 改动文件清单

1. `merco/core/config.py` — 修改默认值 + 新增字段
2. `merco/core/agent.py` — `StreamingProvider.get_response()` 方法
3. `cli/main.py` — REPL 主循环

## 未来扩展

- 如果需要更复杂的 content 显示（比如 Markdown 实时渲染），可以升级到方案 B（content 用 Markdown 渲染器）
- 如果需要 thinking 框在 content 打印完毕后自动清除，可以实现 ANSI 转义码清除逻辑
