# merco 插件化能力分层分析

> 最后更新: 2026-06-26

## 背景

merco 已经完成多个核心基础设施：插件系统、Todo + SubAgent、Memory Save/Recall、Context Pipeline、Observer、HookRegistry、ToolGuard。项目已经从"功能堆叠"进入"架构分层"阶段。

接下来每个能力都应该明确归类为：

1. **原子特性 / Kernel Primitive**：必须稳定、内聚、少扩展，其他能力依赖它。
2. **可拔插特性 / Plugin Extension Point**：可以被插件注册、替换、增强。
3. **应用层插件 / Feature Plugin**：基于扩展点组合出来的具体能力。

本文档梳理 merco 当前特性分层，并指出下一批值得插件化的方向。

---

## 1. 当前应保持"原子特性"的部分

这些是 merco 的内核，不建议让插件随便替换，只能围绕它们扩展。

| 原子特性 | 当前模块 | 为什么是原子 |
|---|---|---|
| Agent Loop | `merco/core/agent.py` | 主循环是核心调度器，不能被插件随意替换 |
| ContextManager | `merco/core/context.py` | 负责消息列表和 token 账本，是数据结构 |
| HookRegistry | `merco/hooks/registry.py` | 事件总线，所有扩展依赖它 |
| PluginManager | `merco/plugins/manager.py` | 插件生命周期内核 |
| SessionStore | `merco/memory/session_store.py` | 会话持久化核心 |
| ToolRegistry | `merco/tools/registry.py` | 工具注册表本身是原子，工具是插件化对象 |
| MercoConfig | `merco/core/config.py` | 配置系统本身是基础设施 |
| TodoManager | `merco/todo/manager.py` | 任务状态机和持久化是原子 |
| SubAgentManager | `merco/agents/subagent.py` | 子代理派发核心是原子 |

这些东西应该"稳定、简单、少魔法"。插件可以调用它们、注册到它们，但不要把它们本身变成随便替换的东西。

---

## 2. 当前已经是"可拔插特性"的部分

这些已经具备插件化雏形。

| 可拔插特性 | 当前扩展点 | 当前状态 |
|---|---|---|
| 工具系统 | `ToolRegistry.register(tool)` | ✅ 已可拔插 |
| Prompt 注入 | `PromptBuilder.use(chunk)` | ✅ 已可拔插 |
| ResultPipeline | `result_pipeline.use(processor)` | ✅ 已可拔插 |
| RecoveryPipeline | `recovery_pipeline.use(recovery)` | ✅ 已可拔插 |
| MemorySavePipeline | `memory_save_pipeline.use(processor)` | ✅ 已可拔插 |
| Memory Recall | `HybridRecaller.add(recaller)` | ✅ 已可拔插 |
| Context Pipeline | `context_pipeline.use(processor)` | ✅ 已可拔插 |
| Hook 事件 | `hooks.on(event, handler)` | ✅ 已可拔插 |
| Todo/SubAgent | `ctx.todo_manager`, `ctx.sub_agent_manager` | ✅ 已暴露给插件 |
| 插件自身 | `Plugin.activate(ctx)` | ✅ 已完成 |

当前 PluginContext 已经比较完整：

```python
PluginContext:
  hooks
  tool_registry
  prompt_builder
  recovery_pipeline
  result_pipeline
  memory_save_pipeline
  recaller
  context_pipeline
  todo_manager
  sub_agent_manager
  observer
  config
```

这已经比 opencode 的"hook slots"更有 merco 特色：**插件不是只监听事件，而是可以直接参与 merco 的处理管线。**

---

## 3. 还可以继续插件化的特性

### A. LLM Provider / Model Adapter 插件化

#### 当前状态

现在 LLM 客户端集中在 `merco/core/llm.py`，`LLMClient` 是 OpenAI-compatible transport。虽然 config 支持 provider，但扩展新 provider 主要还是改 core config / llm 逻辑。

#### 可插件化方向

```python
class ModelProviderPlugin(Plugin):
    async def activate(self, ctx):
        ctx.model_registry.register(MyProvider())
```

新增：

```python
class ModelProvider:
    name: str
    async def chat(...)
    async def chat_stream(...)
```

#### 插件能做什么

- 接入 Anthropic native API
- 接入 Gemini native API
- 接入本地 Ollama
- 接入自建网关
- 接入多模型路由策略

#### 价值判断

**高价值。**

原因：merco 想做 Agent 框架，模型层一定不能被 OpenAI-compatible 限死。

#### 分类

- `LLMClient` 传输基础：原子
- `ModelProvider`：可拔插
- provider 插件：应用层插件

---

### B. Sandbox / Permission Policy 插件化

#### 当前状态

ToolGuard 已经是规则链，但规则主要来自 config。位置在 `merco/sandbox/guard.py`。

#### 可插件化方向

```python
class PermissionPolicy:
    async def check(tool_name, args, context) -> GuardResult:
        ...
```

插件注册：

```python
ctx.permission_pipeline.use(SecurityPolicyPlugin())
```

#### 插件能做什么

- 企业安全策略
- 只读模式
- Git 操作审批
- 文件路径白名单
- 生产环境危险命令拦截
- 审计日志上传

#### 价值判断

**很高价值。**

Agent 的边界之一就是安全。Sandbox 插件化会让 merco 更适合真实工程环境。

#### 分类

- ToolGuard 基础判断：原子
- PermissionPolicy / GuardProcessor：可拔插
- 安全插件：应用层插件

---

### C. Gateway 插件化

#### 当前状态

`merco/gateway/` 已有 `base.py`, `telegram.py`, `discord.py`，但整体还像骨架。

#### 可插件化方向

```python
class GatewayPlugin(Plugin):
    async def activate(self, ctx):
        ctx.gateway_registry.register(TelegramGateway(...))
```

#### 插件能做什么

- Telegram Bot
- Discord Bot
- Slack Bot
- Webhook
- Email
- Web UI
- Local socket / HTTP API

#### 价值判断

**中高价值。**

如果 merco 想从 CLI Agent 变成"多入口 Agent Runtime"，Gateway 插件化非常自然。

#### 分类

- GatewayRuntime：原子
- GatewayAdapter：可拔插
- Telegram/Discord 插件：应用层插件

---

### D. Scheduler 插件化

#### 当前状态

`merco/scheduler/` 有 `cron.py`, `jobs.py`, `delivery.py`，但还没真正成为运行时能力。

#### 可插件化方向

```python
class ScheduledJobPlugin(Plugin):
    async def activate(self, ctx):
        ctx.scheduler.add_job("daily-memory-cleanup", "0 9 * * *", handler)
```

#### 插件能做什么

- 每天总结 session
- 定期清理 memory
- 定期跑代码健康检查
- 自动执行 todo backlog
- 定期触发子代理巡检

#### 价值判断

**高价值，但应该排在 Sandbox / ModelProvider 后。**

Scheduler 和 Todo/SubAgent 结合会很强：定时派发子代理。

#### 分类

- CronScheduler：原子
- Job handler / delivery adapter：可拔插
- 定时任务插件：应用层插件

---

### E. Memory Backend / Indexer 插件化

#### 当前状态

MemoryStore 是 JSON 文件，Recall 有 `MemoryRecaller`, `FTS5Recaller`, `HybridRecaller`。

Recall 已经部分可拔插，但 MemoryStore backend 本身还不是。

#### 可插件化方向

```python
class MemoryBackend:
    save(key, value, tags)
    load(key)
    search(query)
    delete(key)
```

#### 插件能做什么

- SQLite MemoryBackend
- Vector MemoryBackend
- Redis MemoryBackend
- Graph MemoryBackend
- Team-shared MemoryBackend

#### 价值判断

**很高价值，尤其贴合"可靠长短记忆管理系统"。**

这个方向可以成为 merco 的长期特色：**Memory-Native Agent Runtime**。

#### 分类

- Memory API：原子
- MemoryBackend / Recaller / SaveProcessor：可拔插
- 向量记忆/图记忆/团队记忆：应用层插件

---

### F. Slash Command 插件化

#### 当前状态

CLI 命令集中在 `cli/commands.py`。

#### 可插件化方向

```python
ctx.command_registry.register("/foo", handler)
```

#### 插件能做什么

- `/security-scan`
- `/daily-summary`
- `/agent-team`
- `/memory-graph`
- `/export-session`

#### 价值判断

**中价值，体验提升明显。**

现在插件能注册工具，但用户命令层还没插件化。要做插件生态，这个迟早要有。

#### 分类

- CommandRegistry：原子
- Slash command：可拔插
- 插件命令：应用层插件

---

### G. Agent Profile / Role 插件化

#### 当前状态

SubAgentManager 现在有 `agent_name="default"` 的接口，但没有真正的 agent profile 系统。

#### 可插件化方向

```python
class AgentProfile:
    name: str
    prompt: str
    tools: list[str]
    model: str | None
```

插件可以注册：

```python
ctx.agent_registry.register(ResearchAgentProfile())
ctx.agent_registry.register(CodeReviewAgentProfile())
```

#### 插件能做什么

- Researcher
- Planner
- Reviewer
- Debugger
- Security Auditor
- Frontend UI agent

#### 价值判断

**极高价值，和多 Agent 强相关。**

这会让 merco 的子代理派发从"创建一个默认 Agent"升级为"派发专业角色"。

#### 分类

- SubAgentManager：原子
- AgentProfileRegistry：可拔插
- 专业 Agent 插件：应用层插件

---

### H. Response Rendering / UI 插件化

#### 当前状态

Rich Panel / streaming 渲染逻辑在 `merco/core/agent.py` 和 CLI main 里。

#### 可插件化方向

```python
ctx.renderer_registry.register("markdown", MarkdownRenderer())
ctx.renderer_registry.register("compact", CompactRenderer())
```

#### 插件能做什么

- 不同终端 UI
- JSON 输出模式
- TUI 输出模式
- Debug trace 输出
- Thinking panel 风格

#### 价值判断

**中价值。**

但不是核心算法能力，优先级低于 memory / multi-agent / sandbox。

---

### I. Token Estimator / Cost Policy 插件化

#### 当前状态

Token 估算在 `merco/core/context.py`。

#### 可插件化方向

```python
class TokenEstimator:
    estimate_message(msg) -> int
    estimate_prompt(messages, tools) -> int
```

#### 插件能做什么

- Anthropic 精确 token 估算
- OpenAI token 估算
- 本地模型 token 估算
- 成本预算策略

#### 价值判断

**中高价值。**

对长上下文和压缩策略非常关键。

---

## 4. 总体分类图

```text
merco Kernel 原子层
├── Agent Loop
├── HookRegistry
├── PluginManager
├── ContextManager
├── SessionStore
├── ToolRegistry
├── TodoManager
├── SubAgentManager
└── MercoConfig

merco Extension 可拔插层
├── Tools
├── PromptChunks
├── ContextProcessors
├── ResultProcessors
├── RecoveryStrategies
├── MemorySaveProcessors
├── MemoryRecaller
├── MemorySaveStrategy
├── PermissionPolicy       ← 建议新增
├── ModelProvider          ← 建议新增
├── GatewayAdapter         ← 建议新增
├── ScheduledJob           ← 建议新增
├── AgentProfile           ← 强烈建议新增
├── SlashCommand           ← 建议新增
└── TokenEstimator         ← 建议新增

merco Feature Plugins 应用插件层
├── SuperpowerPlugin
├── SecurityScannerPlugin
├── MemoryGraphPlugin
├── TelegramGatewayPlugin
├── AgentTeamPlugin
├── SmartContextPlugin
├── VectorMemoryPlugin
└── CostControlPlugin
```

---

## 5. 下一步插件化优先级建议

### P0：AgentProfile 插件化

因为 merco 已经有 Todo + SubAgent，下一步最自然是：

> 子代理不是 default，而是可注册的专业 Agent Profile。

示例：

```python
ctx.agent_profiles.register(
    AgentProfile(
        name="researcher",
        prompt="你是代码研究员，负责探索和归纳",
        tools=["read_file", "search", "web_search"],
    )
)
```

调用：

```python
ctx.sub_agent_manager.dispatch(todo_id, prompt, agent_name="researcher")
```

这是 **多 Agent 的核心抽象**。

---

### P1：MemoryBackend 插件化

这对应另一个核心方向：可靠长短记忆管理。

目标：

```python
ctx.memory_backends.register(SQLiteMemoryBackend())
ctx.memory_backends.register(VectorMemoryBackend())
```

长期可以做：

- Short-term session memory
- Long-term user memory
- Agent-specific memory
- Shared team memory
- Project memory

---

### P2：PermissionPolicy 插件化

让安全成为插件生态的一部分。

---

### P3：Scheduler / Gateway 插件化

把 merco 从 CLI Agent 变成 Agent Runtime。

---

## 6. 结论

merco 现在已经有不错的插件底座。下一步不要再泛泛做"插件系统"，而是做一个明确的高级扩展点：

## 推荐：AgentProfile 插件化

原因：

1. 直接承接刚完成的 Todo + SubAgent
2. 让多 Agent 成为 merco 特色
3. 可以和插件系统强绑定
4. 工程可控，价值明显
5. 后续 MemoryBackend 可以和 AgentProfile 组合成"记忆型专业 Agent"

下一阶段路线：

```text
Todo + SubAgent
    ↓
AgentProfileRegistry（可拔插专业 Agent）
    ↓
AgentTeam / Agent Orchestration
    ↓
Memory-Native Multi-Agent
```

这个方向最符合 merco 的长期定位：**多 Agent + 可靠长短记忆管理系统**。
