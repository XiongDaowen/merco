# merco 插件化路线图

> 最后更新: 2026-06-27

## 当前进度

| P0: AgentProfile | ✅ 完成 (2026-06-26) |
| P1: MemoryBackend | ✅ 完成 (2026-06-27) |

PluginContext 当前 14 个扩展点。

---

## 剩余待实现

### P2: PermissionPolicy 插件化

**模块**: `merco/sandbox/guard.py` (ToolGuard)

**当前状态**: ToolGuard 规则链 + 30 条默认规则 + config sandbox_rules 扩展。规则主要来自 config 文件，不可插件注册。

**目标**:

```python
class PermissionPolicy(ABC):
    name: str
    async def check(self, tool_name: str, args: dict, context: dict) -> GuardResult: ...

ctx.security_pipeline.use(EnterprisePolicyPlugin())
```

**插件能做什么**:
- 企业安全策略包
- 只读模式
- Git 操作审批链
- 生产环境危险命令拦截
- 文件路径白名单/黑名单
- 审计日志自动上传

| 原子 | 可拔插 | 应用插件 |
|------|--------|---------|
| ToolGuard 基础判断 | PermissionPolicy ABC + PolicyPipeline | SecurityScannerPlugin |

**预估**: 中等工程量，4-6 个任务。核心设计：PermissionPolicy ABC → PolicyPipeline → PluginContext 暴露 → 替换 ToolGuard 硬编码。

---

### P3: ModelProvider 插件化

**模块**: `merco/core/llm.py` (LLMClient)

**当前状态**: `LLMClient` 是 OpenAI-compatible transport。config 支持 provider，但扩展新 provider 需要改 core code。

**目标**:

```python
class ModelProvider(ABC):
    name: str
    async def chat(self, messages, tools, **kwargs) -> dict: ...
    async def chat_stream(self, messages, tools, **kwargs) -> AsyncIterator: ...

ctx.model_registry.register(AnthropicNativeProvider())
```

**插件能做什么**:
- Anthropic native API
- Gemini native API
- 本地 Ollama
- 多模型路由策略（cost/quality/speed）
- 自建网关

| 原子 | 可拔插 | 应用插件 |
|------|--------|---------|
| LLMClient 传输层 | ModelProvider ABC + ModelRegistry | AnthropicNativePlugin |

**预估**: 中高工程量，5-7 个任务。核心设计：ModelProvider ABC → ModelRegistry → 替换 LLMClient 硬编码 provider dispatch。

---

### P4: Scheduler 插件化

**模块**: `merco/scheduler/` (cron.py, jobs.py, delivery.py)

**当前状态**: 骨架已存在（cron/jobs/delivery），但未接入 CLI 运行时。

**目标**:

```python
class ScheduledJobPlugin(Plugin):
    async def activate(self, ctx):
        ctx.scheduler.add_job("daily-summary", "0 9 * * *", handler)
```

**插件能做什么**:
- 每天总结 session
- 定期清理/归档 memory
- 定期跑代码健康检查
- 自动执行 todo backlog
- 定期触发子代理巡检

| 原子 | 可拔插 | 应用插件 |
|------|--------|---------|
| CronScheduler Runtime | ScheduledJob handler | DailySummaryPlugin |

**预估**: 中等工程量，4-5 个任务。核心设计：把已有 cron/jobs 模块接入 CLI 启动 + 暴露给插件。

---

### P5: Gateway 插件化

**模块**: `merco/gateway/` (base.py, telegram.py, discord.py)

**当前状态**: 骨架存在，但整体未实现。

**目标**:

```python
class GatewayPlugin(Plugin):
    async def activate(self, ctx):
        ctx.gateway_registry.register(TelegramBotAdapter(...))
```

**插件能做什么**:
- Telegram Bot
- Discord Bot
- Slack Bot
- Webhook HTTP API
- Local socket

| 原子 | 可拔插 | 应用插件 |
|------|--------|---------|
| GatewayRuntime | GatewayAdapter ABC + GatewayRegistry | TelegramBotPlugin |

**预估**: 较大工程量，6-8 个任务。核心设计：GatewayAdapter ABC → GatewayRegistry → 消息路由 → 多入口 Runtime。

---

### P6: SlashCommand 插件化

**模块**: `cli/commands.py`

**当前状态**: 所有命令硬编码在 `cli/commands.py`，插件无法注册 slash command。

**目标**:

```python
class SlashCommandPlugin(Plugin):
    async def activate(self, ctx):
        ctx.command_registry.register("/security-scan", handler)
```

**插件能做什么**:
- `/security-scan`
- `/daily-summary`
- `/agent-team`
- `/memory-graph`
- `/export-session`

| 原子 | 可拔插 | 应用插件 |
|------|--------|---------|
| CommandRegistry | SlashCommand handler | 插件自定义命令 |

**预估**: 小工程量，3-4 个任务。核心设计：CommandRegistry → 注册 handler → REPL dispatch 改为查 registry。

---

### P7: TokenEstimator 插件化

**模块**: `merco/core/context.py` (estimate_tokens)

**当前状态**: 简单的 CJK/ASCII 启发式估算（1.5 token/字 + 4 字符/token）。

**目标**:

```python
class TokenEstimator(ABC):
    async def estimate(self, text: str) -> int: ...

ctx.token_estimators.register(AnthropicTokenEstimator())
```

**插件能做什么**:
- Anthropic 精确 token 估算
- OpenAI tiktoken
- 本地模型 tokenizer
- 成本预算策略

| 原子 | 可拔插 | 应用插件 |
|------|--------|---------|
| TokenEstimator API | TokenEstimator implementations | AnthropicTokenPlugin |

**预估**: 小工程量，3-4 个任务。核心设计：TokenEstimator ABC → 注册 → ContextManager 使用。

---

### P8: Response Rendering / UI 插件化

**模块**: `merco/core/agent.py` (streaming rendering)

**当前状态**: Rich Panel / streaming 渲染逻辑在 agent.py 和 CLI main。

**目标**:

```python
class OutputRenderer(ABC):
    async def render(self, content: str, metadata: dict) -> None: ...

ctx.renderer_registry.register("compact", CompactRenderer())
```

**插件能做什么**:
- 不同终端 UI 风格
- JSON 输出模式（API 友好）
- TUI 输出模式
- Debug trace 输出

| 原子 | 可拔插 | 应用插件 |
|------|--------|---------|
| Renderer API | Renderer implementations | TUIRendererPlugin |

**预估**: 中等工程量，4-5 个任务。优先级低。

---

## 推荐实施顺序

```
P2: PermissionPolicy  ← 下一步，安全和 ToolGuard 自然延伸
    ↓
P3: ModelProvider     ← 模型层可拔插，核心价值
    ↓
P4: Scheduler         ← 已有 cron 骨架，接入 Runtime
    ↓
P6: SlashCommand      ← 小工程，让插件有 UI 入口
    ↓
P5: Gateway           ← 大工程，多入口 Runtime
    ↓
P7: TokenEstimator    ← 小工程，精确 token 计数
    ↓
P8: UI/Rendering      ← 可选，非核心
```

---

## 完成后 merco 能力矩阵

```
merco Kernel (9 原子特性)
├── Agent Loop
├── HookRegistry
├── PluginManager
├── ContextManager
├── SessionStore
├── ToolRegistry
├── TodoManager
├── SubAgentManager
└── MercoConfig

merco Extension (14-20 可拔插特性)
├── Tools                  ✅
├── PromptChunks           ✅
├── ContextProcessors      ✅
├── ResultProcessors       ✅
├── RecoveryStrategies     ✅
├── MemorySaveProcessors   ✅
├── MemoryRecaller         ✅
├── MemorySaveStrategy     ✅
├── AgentProfiles          ✅
├── MemoryBackends         ✅
├── PermissionPolicy       ← P2
├── ModelProvider          ← P3
├── ScheduledJob           ← P4
├── GatewayAdapter         ← P5
├── SlashCommand           ← P6
├── TokenEstimator         ← P7
└── Renderer               ← P8

merco Plugins (用户/社区)
├── SuperpowerPlugin       ✅
├── SecurityScannerPlugin  ← P2 后可做
├── AnthropicNativePlugin  ← P3 后可做
├── DailySummaryPlugin     ← P4 后可做
├── TelegramBotPlugin      ← P5 后可做
├── VectorMemoryPlugin     ← P1 后续
├── AgentTeamPlugin        ← 后续
└── CostControlPlugin      ← 后续
```
