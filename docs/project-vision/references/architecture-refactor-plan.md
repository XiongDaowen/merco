# merco 架构重构路线图

> 最后更新: 2026-06-28
> 基于: `docs/user_pasted_clipboard_long_content_as_file_# merco 架构审查报告.txt`

## 审查核心发现

1. **PluginContext 安全漏洞** — `security_pipeline` 直接暴露，`add_processor` 无白名单
2. **Agent God Object** — `__init__` 硬初始化 15+ 子系统，边界泄漏
3. **Agent Loop 封闭** — 退出条件硬编码，插件无法注入迭代策略
4. **HookRegistry 单向** — fire-and-forget，插件只能观察不能控制
5. **6 个模块应走插件但硬编码在 Agent**
6. **重复代码** — compressor.py vs compress.py, permissions.py vs guard.py

## P0-P2 已完成回顾

| 优先级 | 特性 | 状态 |
|--------|------|------|
| P0 | AgentProfile 插件化 | ✅ |
| P1 | MemoryBackend 插件化 | ✅ |
| P2 | PermissionPolicy 插件化 | ✅ |

## Phase 1 — 安全加固（P0）✅ 已完成
| 任务 | 内容 | 状态 |
|------|------|------|
| 1.1 PluginContext 安全加固 | 移除 security_pipeline + add_processor 白名单 | ✅ |
| 1.2 activate_all 时序修复 | 先填充 PluginContext 再激活插件 | ✅ |
| 1.3 删除重复代码 | 删除 compressor.py, permissions.py, isolation.py | ✅ |

---

## Phase 2 — 原子能力内聚化（P1）

### 2.1 Agent Loop 开放 LoopPolicy ✅ 已完成

**问题**: `_agent_loop` 退出条件硬编码（agent.py:698），插件无法注入迭代策略。

```python
class LoopPolicy(ABC):
    async def should_continue(self, response: dict, state: LoopState) -> bool: ...
    async def should_exit(self, response: dict, state: LoopState) -> bool: ...

class DefaultLoopPolicy(LoopPolicy):
    name = "default"
    # 复刻当前行为：无 tool_call → 退出
```

| 原子 | 可拔插 | 应用 |
|------|--------|------|
| LoopPolicy ABC | Plugin 可注册 custom policy | LoopEngineeringPlugin |

### 2.2 ToolRegistry 中间件链 ✅ 已完成

**问题**: `registry.execute()` 硬编码 `tool_guard.check()` → core 反向依赖 sandbox。

```python
class ToolMiddleware(ABC):
    async def before(self, tool_name, kwargs) -> dict | None: ...
    async def after(self, tool_name, result) -> dict | None: ...

registry.use(GuardMiddleware(guard))
registry.use(ErrorHandlingMiddleware())
```

| 原子 | 可拔插 | 改动 |
|------|--------|------|
| ToolRegistry 路由 | ToolMiddleware 中间件 | 中等 |

### 2.3 edit.py 移除 sandbox 直接依赖 ✅ 已完成

`edit.py` 直接调用 `confirm_edit()` / `snapshot.track()` → 移到中间件。

### 2.4 Pipeline 内置处理器外移

`pipeline.py` 内置的 WaitRecovery / ContextCompressRecovery / TruncationProcessor 等移到各自的子系统。

### 2.5 self_healing 拆分 ✅ 已完成

`tool_error` 留 core，`llm_error` 归 llm.py。

---

## Phase 3 — 模块插件化迁移（P2）

### 3.1 observability → ObservabilityPlugin

Agent 硬初始化 Observer → 改为 `ObservabilityPlugin` 在 activate 中创建。

```python
class ObservabilityPlugin(Plugin):
    name = "observability"
    async def activate(self, ctx):
        ctx.observer = Observer(ctx.hooks)
        ctx.hooks.on("llm.chat", self._on_llm)
        ...
```

| 原状态 | 迁移后 |
|--------|--------|
| Agent.__init__ 创建 Observer | ObservabilityPlugin.activate() |

### 3.2 skills → SkillPlugin

Agent 硬初始化 SkillRegistry → SkillPlugin。

### 3.3 mcp → MCPPlugin

Agent 硬初始化 MCPServerManager → MCPPlugin。

### 3.4 agents + todo → SubAgentPlugin

Agent 硬初始化 SubAgentManager + TodoManager → SubAgentPlugin。

### 3.5 web_tools → WebPlugin

WebFetch / WebSearch 是拓展而非原子。

### 3.6 scheduler → SchedulerPlugin

已有 cron 骨架，接入 CLI 启动。

### 3.7 HookRegistry 升级 → HookResult + 拦截型 Hook

新增拦截型 hook 入口：
- `llm.before_chat` — 插件可修改 LLM 请求
- `llm.after_chat` — 插件可修改 LLM 响应
- `conversation.turn` — 插件可在每轮结束时注入消息

---

## 实施顺序

```
Phase 1 (P0) — 安全 + 清理
  1.1 PluginContext 安全加固（移除 security_pipeline + 白名单）
  1.2 修复 activate_all 时序
  1.3 删除重复代码（compressor.py, permissions.py, isolation.py）

Phase 2 (P1) — 原子内聚
  2.1 Agent Loop LoopPolicy
  2.2 ToolRegistry 中间件链
  2.3 edit.py 移除 sandbox 依赖
  2.4 Pipeline 处理器外移
  2.5 self_healing 拆分

Phase 3 (P2) — 插件化迁移
  3.1 ObservabilityPlugin
  3.2 SkillPlugin
  3.3 MCPPlugin
  3.4 SubAgentPlugin (+Todo)
  3.5 WebPlugin
  3.6 SchedulerPlugin
  3.7 HookRegistry 升级
```

## 完成后目标架构

```
原子能力 (core)
├── Agent Loop + LoopPolicy
├── ToolRegistry + MiddlewareChain
├── HookRegistry (HookResult + 双向)
├── LLMClient, Session, Context, Message
├── Pipeline 框架, PluginManager, PluginContext
├── MemoryBackend, MemoryStore, SessionStore
├── Sandbox Guard, Snapshot
└── Bash, ReadFile, WriteFile, EditFile

可拓展能力 (plugins)
├── ObservabilityPlugin
├── SkillPlugin
├── MCPPlugin
├── SubAgentPlugin (+Todo)
├── WebPlugin
├── SchedulerPlugin
├── SuperpowerPlugin (示例)
└── 自定义插件
```
