# 中断处理重构 — 设计规格

> 统一 Ctrl+C 中断处理，引入管线模式 + 钩子事件，修复信号处理器冲突、退出逻辑不一致、资源清理不完整等问题。

## 动机

当前 Ctrl+C 处理存在 6 个问题：

1. **信号处理器与输入驱动冲突** — `cli/main.py` 和 `cli/input_driver.py` 都处理 Ctrl+C，导致双重处理
2. **退出逻辑不一致** — `InputInterrupt`、`CancelledError`、`KeyboardInterrupt` 三条路径行为不一致
3. **信号处理器重新注册问题** — 每次循环都重新注册，可能丢失或重复
4. **子进程未清理** — bash 工具的 subprocess 在 task cancel 后继续运行
5. **MCP 连接未关闭** — MCPServerManager 没有 shutdown 方法
6. **统计不一致** — 中断时 observer 数据可能丢失或不完整

## 方案选择

**混合模式（方案 C）** — CLI 层用管线处理中断策略，Agent 层用管线处理清理逻辑。

- CLI 管线负责"响应中断"（取消任务、清空输入、退出进程）
- Agent 管线负责"清理现场"（注入取消消息、kill 子进程、关闭 MCP、发射钩子、保存状态）
- 两个管线通过 `asyncio.Task.cancel()` 连接

## 架构

```
用户按 Ctrl+C
       │
       ▼
┌──────────────────────────────────────────────────────────────┐
│  CLI 层：InterruptPipeline (cli/interrupt.py)                │
│  ┌─────────────────┐  ┌─────────────────┐  ┌──────────────┐ │
│  │ CancelTask      │→│ ClearInput      │→│ ExitWithHooks│ │
│  │ Strategy        │  │ Strategy        │  │ Strategy     │ │
│  └─────────────────┘  └─────────────────┘  └──────────────┘ │
└──────────────────────────────────────────────────────────────┘
       │ (Agent 运行中时触发 CancelledError)
       ▼
┌──────────────────────────────────────────────────────────────┐
│  Agent 层：InterruptCleanupPipeline (merco/core/interrupt.py)│
│  ┌─────────────┐  ┌──────────────┐  ┌───────────┐  ┌──────┐ │
│  │ InjectCancel │→│ KillSubproc  │→│ CloseMCP   │→│ Emit │ │
│  │ Messages     │  │ esses        │  │ Connections│  │ Hooks│ │
│  └─────────────┘  └──────────────┘  └───────────┘  └──────┘ │
│       │                                              │      │
│       │            ┌──────────────┐                  │      │
│       └───────────→│ SavePartial  │←─────────────────┘      │
│                    │ State        │                         │
│                    └──────────────┘                         │
└──────────────────────────────────────────────────────────────┘
```

## 核心组件

### CLI 层：InterruptPipeline

```python
# cli/interrupt.py

class InterruptState(Enum):
    """中断时的系统状态。"""
    IDLE = "idle"              # 输入框为空
    INPUT_HAS_TEXT = "input"   # 输入框有内容
    AGENT_RUNNING = "agent"    # Agent 任务运行中


@dataclass
class InterruptContext:
    """中断处理上下文。"""
    state: InterruptState
    task: asyncio.Task | None = None
    exit_count: int = 0        # 二次确认计数器
    handled: bool = False


class InterruptStrategy(ABC):
    """中断处理策略基类。"""
    name: str = ""

    @abstractmethod
    async def handle(self, ctx: InterruptContext) -> bool:
        """返回 True 表示已处理，停止管线。"""
        ...


class InterruptPipeline:
    """中断处理管线。按优先级依次尝试各策略。"""

    def __init__(self):
        self._strategies: list[InterruptStrategy] = []

    def use(self, strategy: InterruptStrategy) -> "InterruptPipeline":
        self._strategies.append(strategy)
        return self

    async def process(self, ctx: InterruptContext) -> None:
        for strategy in self._strategies:
            try:
                if await strategy.handle(ctx):
                    return
            except Exception:
                logger.warning("中断策略 '%s' 异常", strategy.name, exc_info=True)
```

### 三个策略

| 策略 | 触发条件 | 行为 |
|------|----------|------|
| `CancelTaskStrategy` | `state == AGENT_RUNNING` | 调用 `task.cancel()`，设置 `_interrupting` 防重入 |
| `ClearInputStrategy` | `state == INPUT_HAS_TEXT` | 通过回调函数清空 prompt_toolkit 缓冲区（由 input_driver 注入） |
| `ExitWithHooksStrategy` | `state == IDLE` | exit_count=0 提示，exit_count=1 执行退出钩子 + `sys.exit()` |

**ClearInputStrategy 实现：**

```python
class ClearInputStrategy(InterruptStrategy):
    """清空输入框。"""
    name = "clear_input"

    def __init__(self, on_clear: Callable[[], None]):
        """on_clear: 由 PromptToolkitInput 注入的清空回调。"""
        self._on_clear = on_clear

    async def handle(self, ctx: InterruptContext) -> bool:
        if ctx.state != InterruptState.INPUT_HAS_TEXT:
            return False
        self._on_clear()
        ctx.handled = True
        return True
```

**回调注入：**

```python
# cli/main.py 中构建 InterruptPipeline 时
def _clear_input_buffer():
    driver._session.default_buffer.text = ""

interrupt_pipeline = (InterruptPipeline()
    .use(CancelTaskStrategy())
    .use(ClearInputStrategy(_clear_input_buffer))
    .use(ExitWithHooksStrategy(_exit_gracefully)))
```

### Agent 层：InterruptCleanupPipeline

```python
# merco/core/interrupt.py

@dataclass
class CleanupContext:
    """中断清理上下文。"""
    agent: "Agent"
    cancelled_tool_calls: list[dict]
    session_id: str
    results: dict[str, Any] = field(default_factory=dict)


class CleanupProcessor(ABC):
    """清理处理器基类。"""
    name: str = ""

    @abstractmethod
    async def process(self, ctx: CleanupContext) -> bool:
        """返回 True 表示已处理，停止管线。"""
        ...


class InterruptCleanupPipeline:
    """中断清理管线。"""

    def __init__(self):
        self._processors: list[CleanupProcessor] = []

    def use(self, processor: CleanupProcessor) -> "InterruptCleanupPipeline":
        self._processors.append(processor)
        return self

    async def process(self, ctx: CleanupContext) -> None:
        for processor in self._processors:
            try:
                if await processor.process(ctx):
                    return
            except Exception:
                logger.warning("清理处理器 '%s' 异常", processor.name, exc_info=True)
```

### 五个处理器

| 处理器 | 职责 | 实现 |
|--------|------|------|
| `InjectCancelMessages` | 为孤儿 tool_calls 注入"取消 (Ctrl+C)"消息 | 遍历 context.messages，找未完成的 tool_call_id |
| `TerminateSubprocesses` | kill 所有运行中的子进程 | BashTool 跟踪活跃进程，逐一 kill |
| `CloseMCPConnections` | 关闭 MCP 连接 | 调用 `mcp_manager.shutdown()` |
| `EmitInterruptHooks` | 发射 `agent.interrupted` 钩子 | `await hooks.emit("agent.interrupted", ...)` |
| `SavePartialState` | 保存 session + observer 快照 | `session.save()` + `_session_store.save_metadata()` |

## 数据流

### 场景 1：Agent 运行中按 Ctrl+C

```
1. 用户按 Ctrl+C
2. 信号处理器触发 handle_interrupt()
3. InterruptPipeline.process(AGENT_RUNNING)
4. CancelTaskStrategy → task.cancel()
5. Agent._agent_loop() 捕获 CancelledError
6. Agent.run() 捕获 CancelledError
7. InterruptCleanupPipeline.process(ctx)
   a. InjectCancelMessages → 注入取消消息
   b. TerminateSubprocesses → kill bash 子进程
   c. CloseMCPConnections → 关闭 MCP 连接
   d. EmitInterruptHooks → observer 统计中断
   e. SavePartialState → 保存 session/observer
8. REPL 捕获 CancelledError → 继续输入循环
```

### 场景 2：输入框有内容时按 Ctrl+C

```
1. 用户按 Ctrl+C
2. prompt_toolkit 的 Ctrl+C 绑定触发
3. 清空输入缓冲区（不抛 InputInterrupt）
4. 信号处理器也触发
5. InterruptPipeline.process(INPUT_HAS_TEXT)
6. CancelTaskStrategy → state != AGENT_RUNNING，跳过
7. ClearInputStrategy → 缓冲区已空（步骤 3 已清空），跳过
8. ExitWithHooksStrategy → state != IDLE，跳过
9. 管线结束，无操作
```

### 场景 3：输入框为空时按 Ctrl+C（第一次）

```
1. 用户按 Ctrl+C
2. prompt_toolkit 的 Ctrl+C 绑定触发
3. 抛出 InputInterrupt
4. REPL 捕获 InputInterrupt
5. 设置 exit_count = 1，提示"再按一次退出"
6. 3 秒后自动重置 exit_count = 0
```

### 场景 4：输入框为空时按 Ctrl+C（第二次）

```
1. 用户按 Ctrl+C
2. prompt_toolkit 的 Ctrl+C 绑定触发
3. 抛出 InputInterrupt
4. REPL 捕获 InputInterrupt
5. exit_count == 1，执行退出流程
6. 移除信号处理器
7. 执行退出钩子（保存 session/observer，恢复 termios，关闭 MCP）
8. sys.exit(0)
```

## 退出行为

### 优雅退出 + 二次确认

```
用户按 Ctrl+C（输入框为空）
       │
       ▼
┌─────────────────────────────────────────┐
│  exit_count == 0 ?                      │
│  ├── 是 → 提示"再按一次退出"            │
│  │         exit_count = 1               │
│  │         3秒后自动重置 exit_count = 0  │
│  │                                      │
│  └── 否 → 执行退出流程                  │
└─────────────────────────────────────────┘
```

### 退出钩子执行顺序（LIFO）

```python
_on_exit(lambda: agent.mcp_manager.shutdown())        # 1. 关闭 MCP
_on_exit(lambda: agent._session_store.save_metadata()) # 2. 保存 metadata
_on_exit(lambda: agent.session.save())                 # 3. 保存 session
_on_exit(lambda: agent.observer.save())                # 4. 保存 observer
_on_exit(lambda: termios.tcsetattr(0, ...))            # 5. 恢复 termios
```

### 超时保护

- 3 秒无操作自动重置 exit_count（防止误触后一直保持"待退出"状态）
- 退出钩子执行超时 5 秒强制 `os._exit(1)`

## 统计处理

### Observer 新增钩子

```python
# Observer 中新增监听
hooks.on("agent.interrupted", self._on_interrupt)

def _on_interrupt(self, interrupted_tools: int = 0, **kwargs):
    """中断时记录统计。"""
    if interrupted_tools:
        self._live.increment("tool_calls_interrupted", interrupted_tools)
        self._live.increment("tool_calls", interrupted_tools)  # 计入总工具调用
    self._live.increment("turns")  # 补计 turn
    self._merge_to_acc()  # 立即合并到累计
```

### report 输出新增中断统计

```python
# observer.report() 中
interrupted = live.get_counter("tool_calls_interrupted")
if interrupted:
    lines.append(f"       [yellow]中断: {interrupted} 次工具调用[/yellow]")
```

## 边界场景处理

### 场景 1：子进程未清理

**问题：** bash 工具的 subprocess 在 task cancel 后继续运行。

**修复：** BashTool 跟踪活跃进程，中断时 kill。

```python
class BashTool(BaseTool):
    _active_processes: set[asyncio.subprocess.Process] = set()

    async def execute(self, command: str, ...) -> dict:
        process = await asyncio.create_subprocess_shell(command, ...)
        self._active_processes.add(process)
        try:
            ...
        finally:
            self._active_processes.discard(process)

    def kill_all(self):
        for proc in self._active_processes:
            try:
                proc.kill()
            except ProcessLookupError:
                pass
        self._active_processes.clear()
```

### 场景 2：流式响应未关闭

**问题：** 中断后流式响应继续输出。

**修复：** StreamingProvider 检查 task cancelled 状态。

```python
class StreamingProvider(ResponseProvider):
    async def get_response(self, agent, messages, tools) -> dict:
        stream = agent.llm.chat_stream(messages, tools=tools)
        async for chunk in stream:
            if asyncio.current_task().cancelled():
                break  # 中断时退出流式循环
            ...
```

### 场景 3：MCP 连接未关闭

**问题：** MCPServerManager 没有 shutdown 方法。

**修复：** 添加 `shutdown()` 方法。

```python
class MCPServerManager:
    async def shutdown(self):
        """关闭所有 MCP 连接。"""
        for name in list(self._servers.keys()):
            await self.disconnect(name)
```

### 场景 4：连续快速按 Ctrl+C

**问题：** 多次触发中断处理。

**修复：** 添加 `_interrupting` 标志防止重入。

```python
class CancelTaskStrategy(InterruptStrategy):
    async def handle(self, ctx: InterruptContext) -> bool:
        if ctx.state != InterruptState.AGENT_RUNNING or not ctx.task:
            return False
        # 防止重入
        if getattr(ctx.task, '_interrupting', False):
            return True
        ctx.task._interrupting = True
        ctx.task.cancel()
        ctx.handled = True
        return True
```

### 场景 5：edit_file 确认提示期间中断

**问题：** 用户在确认提示期间按 Ctrl+C。

**修复：** 确认对话框捕获 KeyboardInterrupt 并返回拒绝。

```python
# merco/sandbox/confirm.py
async def confirm_edit(...) -> bool:
    try:
        ...
    except KeyboardInterrupt:
        return False  # 拒绝编辑
```

### 场景 6：中断时补全菜单显示

**问题：** 补全菜单关闭后是否需要再次触发中断。

**修复：** prompt_toolkit 的 Ctrl+C 绑定先关闭补全菜单，再处理中断。

## 错误处理

| 异常 | 处理 |
|------|------|
| 策略/处理器异常 | 记录日志，继续下一个 |
| 退出钩子异常 | 捕获并忽略，继续执行 |
| 退出钩子超时 | 5 秒后强制 `os._exit(1)` |

## 测试策略

### 单元测试

| 测试 | 覆盖 |
|------|------|
| `test_interrupt_pipeline_*` | InterruptPipeline 的策略执行顺序 |
| `test_cancel_task_strategy` | CancelTaskStrategy 的触发条件和防重入 |
| `test_exit_with_hooks_strategy` | 二次确认逻辑 |
| `test_cleanup_pipeline_*` | InterruptCleanupPipeline 的处理器执行顺序 |
| `test_inject_cancel_messages` | 孤儿 tool_calls 的注入逻辑 |
| `test_observer_interrupt_hook` | 中断统计的正确性 |

### 集成测试

| 测试 | 覆盖 |
|------|------|
| `test_repl_interrupt_during_agent` | Agent 运行中按 Ctrl+C 的完整流程 |
| `test_repl_interrupt_empty_input` | 输入框为空时的退出流程 |
| `test_repl_interrupt_double_ctrlc` | 连续快速按 Ctrl+C |

## 改动文件

| 文件 | 改动 |
|------|------|
| `cli/interrupt.py` | **新建**：InterruptPipeline + InterruptStrategy + 三个策略 |
| `merco/core/interrupt.py` | **新建**：InterruptCleanupPipeline + CleanupProcessor + 五个处理器 |
| `cli/main.py` | 用 InterruptPipeline 替换信号处理器，添加退出钩子 |
| `cli/input_driver.py` | 调整 Ctrl+C 绑定，与 InterruptPipeline 配合 |
| `merco/core/agent.py` | 用 InterruptCleanupPipeline 替换 `_inject_interrupted_tool_results`，捕获 CancelledError |
| `merco/tools/bash_tools.py` | 添加子进程跟踪和 kill_all 方法 |
| `merco/mcp/manager.py` | 添加 shutdown 方法 |
| `merco/observability/observer.py` | 添加 `agent.interrupted` 钩子监听 |
| `merco/sandbox/confirm.py` | 捕获 KeyboardInterrupt |

## 演进方向

- **Phase 4 TUI**：Textual TUI 实现自己的 InterruptStrategy
- **插件化**：第三方可通过 `interrupt_pipeline.use()` 添加自定义策略
- **远程 Agent**：中断信号可通过 WebSocket 传递到远程 Agent
