# 🧠 merco — Mercury Code

> **Mer**(cury) + **Co**(de) = 默客 — 一个轻量、可拓展的 AI 编程助手，跑在你的终端里。

`pip install merco && merco` 就能开始。没有 Docker、没有数据库依赖。架构上就是一个 Agent 循环 + 插件系统——你需要的功能全是你自己选的插件。

---

## 🪶 轻量

```bash
pip install merco       # 安装
merco setup             # 首次运行交互引导（选平台 / 填 Key / 选模型）
merco                   # 启动 REPL
```

**一条命令安装，一条命令启动。** 配置文件是可选的——环境变量 `OPENAI_API_KEY` 或 `OPENROUTER_API_KEY` 就够了。底层 Python 3.12+ 原生 asyncio，uv 构建。

---

## 🔌 插件拓展

**merco 的所有子系统都是插件。** 8 个内置插件全部通过 `pyproject.toml` 的 `entry_points` 动态发现，零硬编码。你可以关掉任何一个、或用自己的替代——也可以注册全新的。

```python
from merco.plugins.base import Plugin, PluginContext

class MyPlugin(Plugin):
    name = "my_plugin"
    priority = 50                    # 越大越早激活（默认 50）
    version = "1.0.0"

    async def activate(self, ctx: PluginContext) -> None:
        # ctx 暴露 20+ 子系统引用 + 一组便捷方法
        ctx.hooks.on("agent.start", self._on_start)        # 订阅事件
        ctx.register_tool(MyTool())                        # 注册工具
        ctx.register_model_provider(MyProviderInfo)         # 注入你的模型
        ctx.register_gateway(TelegramGateway())             # 注入你的网关
        ctx.add_processor("result_pipeline", MyProcessor()) # 接管管线
```

### 内置插件

| 插件 | priority | 做什么 |
|------|:--:|------|
| **Observability** | **100** | 创建 Observer，boot 阶段最先激活 |
| **Skills** | 60 | 加载 SKILL.md，注入 system prompt |
| **MCP** | 50 | MCPServerManager，自动连接 MCP 服务器 |
| **SubAgent** | 40 | 子 Agent 派发 + Todo 任务分解 |
| **Web** | 30 | 注册 web_fetch / web_search 工具 |
| **Gateway** | 25 | 注册内置 WebhookGateway（FastAPI，port 自动分配） |
| **Scheduler** | 20 | 创建 CronScheduler，AgentRuntime 后台调度 |
| **Superpower** | 10 | 事件注入、self-healing |

### 三行装上

```toml
# 在你的 pyproject.toml 里：
[project.entry-points."merco.plugins"]
my_plugin = "my_package.my_plugin:MyPlugin"
```

merco 安装即被发现。也支持目录扫描（扔一个 `plugin.toml` 到 `~/.config/merco/plugins/` 下）和 `merco.json` 的 `plugins` 字段手动切 enabled / 传自定义 config。

### 还要怎么拓展？

| 你想做的事 | 用这个 |
|------------|--------|
| 接一个新的 LLM 供应商 | `ctx.register_model_provider(info)` |
| 接一个消息平台（Telegram/Discord/...） | `ctx.register_gateway(adapter)` |
| 加一套新的工具（Bash 之外的） | `ctx.register_tool(tool)` |
| 给 system prompt 注入一段 | `ctx.add_prompt_chunk(chunk)` |
| 对 agent 输出做后处理 | `ctx.add_processor("result_pipeline", proc)` |
| 加一个记忆存储后端 | `ctx.add_memory_backend(backend)` |
| 加一个安全策略 | `ctx.add_security_policy(policy)` |
| 订阅生命周期事件 | `ctx.hooks.on("event", handler)` |

---

## 🏗️ 架构一览

```
CLI   Webhook   Cron   Custom
 |       |        |       |
 +-------+--------+-------+
         |
         v
   AgentRuntime
         |
         v
   Agent Loop
    |   |   |   |
    v   v   v   v
  LLM Tools Mem Plugins
```

- **AgentRuntime** — 统一生命周期。`start()` 触发插件两阶段激活 + gateway/scheduler 启动；`stop()` 幂等收尾。CLI / webhook / cron / 任何入口都通过它调用 Agent。
- **ModelProvider ABC** + **ModelRegistry** — 多模型层。内置 OpenAI / Anthropic / 任意 OAI-兼容端点（填 `base_url` 就行）。`select()` 独占凭证解析，Agent 不感知 `api_key`。
- **GatewayAdapter ABC** + **GatewayRegistry** — 多入口接入。内置 `WebhookGateway`（FastAPI/uvicorn，`port=0` OS 自动分配，POST `/message` → `{reply}`）。注册你的 adapter 后 Runtime 自动接管 inbound/outbound；单个 gateway 启动失败不影响其他。
- **CronScheduler** — 定时任务，由 SchedulerPlugin 创建，Runtime 自动后台 `asyncio.create_task` 拉起。

---

## ⚙️ 配置示例

最小即可跑（其余字段均有合理默认值）：

```json
{"model": {"provider": "openai", "model": "gpt-4", "api_key": "sk-..."}}
```

<details>
<summary>展开完整配置示例</summary>

```json
{
  "username": "user",
  "model": {
    "provider": "openai",
    "model": "gpt-4",
    "api_key": null,
    "base_url": null,
    "temperature": 0.7,
    "max_tokens": 4096,
    "extra_params": {},
    "headers": {},
    "request_cooldown": 0.3,
    "fallbacks": [
      {
        "provider": "anthropic",
        "model": "anthropic/claude-sonnet-4",
        "temperature": 0.7,
        "max_tokens": 4096
      }
    ]
  },

  "max_tool_calls": 50,
  "max_input_tokens": 64000,
  "compression_threshold": 0.75,

  "streaming": {
    "enabled": false,
    "think": true,
    "content": true,
    "think_transient": false,
    "render_interval": 0.05
  },

  "skills_paths": ["./.merco/skills", "~/.config/merco/skills"],
  "plugins_paths": ["./.merco/plugins", "~/.config/merco/plugins"],

  "memory": {
    "enabled": true,
    "path": "~/.merco/memory",
    "backend": "json",
    "recall_enabled": true,
    "recall_limit": 3,
    "recall_max_chars": 300
  },

  "session": {"fork_enabled": true, "fork_auto_on_compress": true},
  "sandbox_mode": "ask",
  "diff_view": "unified",
  "mcp_servers": {},
  "log_level": "INFO"
}
```

</details>

---

<details>
<summary>🗂️ 完整命令列表（27 个 /command）</summary>

| 组 | 命令 | 说明 |
|----|------|------|
| **info** | `/help` `/model` `/context` `/tools` `/report` `/reload-mcp` `/mcp-status` | 帮助、模型、上下文用量、工具列表、统计报告、MCP 重载与状态 |
| **session** | `/new` `/sessions` `/fork` `/tree` `/history` `/revert` | 新建会话、历史列表+切换、分支、查看历史、回滚文件修改 |
| **search** | `/search` `/recall` | 搜索历史消息、召回相关内容 |
| **memory** | `/remember` `/memories` `/forget` | 存记忆、列出记忆、删除记忆 |
| **system** | `/plugins` | 列出已安装插件（状态+版本） |
| **task** | `/todos` `/todo` `/todo-done` `/agents` `/agent` | 任务列表、任务详情、完成任务、AgentProfile 列表与详情 |
| **control** | `/exit` `/quit` `/q` | 退出（自动保存 session + observer snapshot） |

</details>

---

<details>
<summary>🏗️ 模块状态总览</summary>

| 模块 | 状态 | 说明 |
|------|:---:|------|
| Agent Loop | 🟢 POLISHED | turn-loop + 工具调用调度 |
| Tools | 🟢 POLISHED | Bash / File / Edit / Web / MCP / Skill / Task |
| Skills | 🟢 POLISHED | SkillLoader + SkillRegistry |
| MCP | 🟢 POLISHED | MCPServerManager + MCPPlugin |
| Memory | 🟢 POLISHED | Save + Recall (HybridRecaller: FTS5 + JSON) |
| Context | 🟢 NEW | ContextPipeline + CompressProcessor |
| Hooks | 🟢 POLISHED | HookRegistry，15+ 事件 |
| Sandbox | 🟢 POLISHED | ToolGuard 28 规则 + SecurityChecker + Snapshot |
| Observability | 🟢 POLISHED | hooks 驱动 Observer |
| Scheduler | 🟢 POLISHED | CronScheduler，Runtime 后台启动 |
| Plugins | 🟢 NEW | entry_points + 目录扫描，8 内置插件 |
| SubAgent | 🟢 NEW | SubAgentManager + AgentProfileRegistry |
| Todo | 🟢 NEW | TodoItem + TodoManager |
| Gateway | 🟢 NEW | GatewayAdapter ABC + GatewayRegistry + WebhookGateway |

</details>

---

<details>
<summary>📁 完整项目结构</summary>

```
merco/
├── agents/         # AgentProfile + SubAgentManager
├── cli/            # REPL 入口（main, commands, registry, input_driver, interrupt）
├── core/           # Agent 循环 + LLM + Runtime + Config + Session
│   ├── agent.py        # turn-loop
│   ├── runtime.py      # AgentRuntime（start/stop/submit/handle_inbound）
│   ├── llm/            # ModelProvider ABC + ModelRegistry + 双 provider
│   └── pipeline.py     # RecoveryPipeline / ResultPipeline
├── gateway/        # GatewayAdapter ABC + GatewayRegistry + WebhookGateway
├── hooks/          # HookRegistry（15+ 事件）
├── mcp/            # MCP 客户端（manager / config / tool）
├── memory/         # MemoryStore + HybridRecaller + SessionStore (SQLite WAL)
├── observability/  # Observer / metrics / audit
├── plugins/        # 插件系统（base / discovery / manager / builtin/）
├── sandbox/        # ToolGuard / SecurityChecker / Snapshot
├── scheduler/      # CronScheduler
├── skills/         # SkillLoader + 内置 SKILL.md
├── tools/          # Bash / File / Web / MCP / Skill / Task / Edit
├── todo/           # TodoManager
└── utils/          # 通用工具
```

</details>

---

## 📖 文档

- 模块状态总览 → [`docs/project-vision/references/architecture.md`](docs/project-vision/references/architecture.md)
- 项目进展与决策记录 → [`docs/project-vision/references/progress.md`](docs/project-vision/references/progress.md)
- 下一个投入方向 → [`docs/project-vision/references/next-focus.md`](docs/project-vision/references/next-focus.md)

## 📄 许可证

MIT
