# 架构设计

## 必须保留的核心模块

| 模块 | 说明 |
|------|------|
| Agent-Loop | 主循环与工具调用调度 |
| Skills | 可扩展技能系统 |
| Tools | 文件/终端/网络等基础工具 |
| MCP | 模型上下文协议支持 |
| Memory | 自动记忆与召回 |
| Context | 上下文压缩与管理 |
| Hooks | 生命周期钩子 |
| Sandbox | 权限与沙箱控制 (目标: 容器化隔离) |
| Observability | 日志与可观测性 |
| Scheduler | 定时任务调度 |

### 可以裁剪的部分

- 过度抽象的配置系统
- 不常用的消息平台集成
- 复杂的插件加载机制
- 冗余的中间层封装

## 项目目录结构

```
openmercury/
├── core/           # 核心引擎 (agent, session, message, context, config)
├── tools/          # 工具系统 (registry, file, bash, web, task, mcp)
├── skills/         # 技能系统 (loader, registry, builtin/)
├── memory/         # 记忆系统 (store, recall, compressor, search)
├── hooks/          # 钩子系统 (registry, lifecycle, tool, chat)
├── sandbox/        # 沙箱环境 (permissions, isolation, security)
├── scheduler/      # 定时任务 (cron, jobs, delivery)
├── observability/  # 可观测性 (logger, metrics, tracing, audit)
├── gateway/        # 消息网关 (base, telegram, discord, web)
└── utils/          # 工具函数

cli/                # CLI 入口 (main, commands, tui)
web/                # Web 界面 (FastAPI app)
tests/              # 测试 (unit, integration, fixtures)
docs/               # 文档
config/             # 配置示例
references/         # 参考源码 (git 忽略)
```

## 技术栈

- **语言**: Python 3.12+
- **包管理**: uv
- **异步**: asyncio / aiohttp
- **CLI**: typer / click
- **TUI**: textual / rich
- **Web**: fastapi
- **配置**: pydantic-settings
- **测试**: pytest

## 参考资料库

`references/` 文件夹包含三个核心参考项目 (git 忽略，不提交):

| 项目 | 路径 | 说明 |
|------|------|------|
| **Hermes Agent** | `references/hermes-agent/` | Nous Research 开发的自改进 AI Agent，具备记忆系统、Skill 自动创建、多平台网关等特性 |
| **OpenClaw** | `references/openclaw/` | 个人 AI 助手框架，支持多平台、插件系统、定时任务等 |
| **OpenCode** | `references/opencode/` | 终端 AI 编码助手，提供 TUI、Skill 系统、MCP 集成等 |

 实现功能时优先参考这些项目的源码。

## 模块集成架构

各子模块应通过 Agent Loop 完成调用链连接（当前状态：代码存在但连接断开）:

```
Agent.run(prompt)
  │
  ├─ Hooks → emit("agent.start")
  ├─ Memory.Recall → 注入相关记忆
  ├─ Skills.RelevantSkills → 注入到 system prompt
  │
  └─ _agent_loop()
       │
       ├─ Hooks → emit("tool.before")             ← 未连接
       ├─ Sandbox.Permissions.check()             ← 未连接
       ├─ Sandbox.Security.check_command()        ← 未连接
│       ├─ ToolRegistry.execute() + Sandbox隔离    ← 未连接
       ├─ Observability.Metrics.record()          ← 未连接
       ├─ Observability.Audit.log()               ← 未连接
       ├─ Hooks → emit("tool.after")              ← 未连接
       │
       ├─ _ask_continuation() → LLM 自评续命       ← ✅ 已实现 (max_tool_calls)
       │
       └─ Memory.Store.save() → 持久化会话        ← 未连接
```

## 架构模式

### Tool Error Resilience (registry try/except)

工具执行通过 `ToolRegistry.execute()` 统一入口。所有异常在此捕获并转为结构化错误：

```
TypeError → {error, available_params, received_params}  # LLM 自愈
Exception → {error: "TypeName: message"}                 # 通用兜底
```

错误以工具结果形式喂回 LLM，绝不 propagate 中断 agent 循环。

### Continuation Evaluation (_ask_continuation)

通用续命架构：任何预算耗尽时，让 LLM 自评是否继续。

```
触发点（max_tool_calls / retry_limit / token_budget / permission_deny）
  → _ask_continuation(limit_type, current, maximum)
    → 注入评估 prompt（无 tools）
    → LLM 回复 "CONTINUE:N" → 扩展预算，继续循环
    → LLM 回复 最终回答 → 直接返回
```

设计原则：
- 单一入口 `_ask_continuation()`，参数化决策 prompt
- LLM 是决策者而非执行机器
- 预算扩展后 context 不残留决策对话（CONTINUE 回复仅用于控制流）
- 可复用至任何资源限制场景
