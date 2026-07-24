# 🧠 merco — Mercury Code

> **Mer**(cury) + **Co**(de) = 默客 — 默默写代码的 AI 伙伴

一个插件化、多模型、多入口接入的 Python 智能开发助手，运行在你的终端里。核心是一个 Agent 主循环，通过 `merco.plugins` entry-points 动态发现的 8 个内置插件组合出完整工作面：Skills / MCP / SubAgent / Web / Scheduler / Gateway / Observability / Superpower，Model layer 用 `ModelRegistry` 单一真相源管理多个 `ModelProvider`（OpenAI/Anthropic/OAI-兼容），Gateway 层用 `GatewayRegistry` + 内置 `WebhookGateway` 提供 webhook 入站，把 CLI 与 webhook 收口到同一个 `AgentRuntime` 生命周期宿主里。

---

## ✨ 特性亮点

| 功能 | 说明 |
|------|------|
| 🤖 **Agent 循环** | 用户输入 → LLM → 工具调用 → 循环；`agent.py` 实现 turn-loop；CLI / webhook / 定时任务共用同一套生命周期管理 |
| 🖥️ **流式输出** | thinking/content 双面板，`StreamingConfig` 子对象（`enabled/think/content/think_transient/render_interval`）分级控制 |
| 🔌 **插件系统** | `PluginDiscovery`（entry-points `merco.plugins` + 目录扫描）→ `PluginManager`（Kahn 拓扑 + priority）→ 8 个内置插件，**全部 entry-points 动态发现** |
| 🧠 **多模型接入** | `ModelProvider` ABC + `ModelRegistry` 单一真相源；内置 `OpenAICompatibleProvider` / `AnthropicNativeProvider`；凭证解析由 `select()` 独占，Agent 不感知 base_url/api_key |
| 🌐 **Webhook Gateway** | `GatewayAdapter` ABC + `GatewayRegistry` 生命周期管理；内置 `WebhookGateway`（FastAPI/uvicorn，`port=0` OS 自动分配，POST `/message`）；失败隔离 |
| ⏰ **Scheduler** | `CronScheduler` 由 `SchedulerPlugin` 注入到 `PluginContext`，通过 `AgentRuntime.start()` 后台 `asyncio.create_task` 启动 |
| 🛡️ **安全守卫** | `ToolGuard` 规则链，默认 28 条 ask 规则，`sandbox_mode` 可切 `ask` / `auto` / `deny`；`/revert` 可回滚本会话文件修改 |
| 💾 **Session 记忆** | `SessionStore` 用 SQLite WAL 模式，支持并发读 + 增量写 + FTS5 全文搜索；`/sessions` 切换、`/fork` 创建分支、`/history` 分页查看 |
| 🧠 **Memory Recall** | `HybridRecaller`（FTS5 + JSON 后端）自动召回相关记忆 + 历史会话内容 |
| 📊 **可观察性** | hooks 驱动 `Observer`（订阅 7+ 事件）；`/report` 显示 token 统计、LLM 延迟、工具分布、`/report reset` 清零 |
| 🚀 **代码质量** | `ruff` lint + format（`ruff check .` 0 问题）；`pre-commit` 钩子强制（提交前自动检查）；**999 测试全绿** |

---

## 🚀 快速开始

```bash
# 安装
pip install merco
# 或
uv tool install merco

# 交互式配置（首次运行引导，选择平台 / 填 Key / 选模型）
merco setup

# 启动 REPL
merco

# 指定模型临时启动
merco run -m claude-sonnet-4-20250514 -k sk-...

# 程序化入口（供脚本调用）
merco-web  # Web API 预留
```

> **配置文件加载顺序**（后者覆盖前者）：
> 1. `<cwd>/merco.json`（项目级）
> 2. `<cwd>/.merco/merco.json`（项目级隐藏）
> 3. `~/.config/merco/config.json`（用户级）
> 同时支持环境变量：`OPENAI_API_KEY` / `OPENROUTER_API_KEY` 缺省时自动 fall-back。

> **子命令**：
> - `merco` / `merco run` —— 启动交互式 REPL
> - `merco init` —— 在当前目录创建默认 `merco.json`
> - `merco skills -l` —— 列出已加载技能
> - `merco setup` —— 启动交互式配置向导

---

## 📁 项目结构

```
merco/
├── agents/         # AgentProfile + SubAgentManager（子 Agent 派发）
├── cli/            # REPL 入口（main, commands, registry, input_driver, interrupt）
├── config/         # 配置示例
├── context/        # ContextPipeline + CompressProcessor / CacheOptimizeProcessor
├── core/           # Agent 主循环 + Config + Session + LLM + Runtime
│   ├── agent.py        # turn-loop 主心骨（工具调用循环 + 上下文管理）
│   ├── runtime.py      # AgentRuntime 生命周期宿主（start/stop/submit/handle_inbound）
│   ├── config.py       # MercoConfig / ModelConfig / StreamingConfig（dataclass）
│   ├── llm/            # ModelProvider ABC + ModelRegistry（单一真相源）
│   │   ├── base.py             # ModelProvider ABC + ModelProviderInfo
│   │   ├── registry.py         # ModelRegistry：select()/register()/list()
│   │   ├── openai_provider.py  # OpenAICompatibleProvider（吸收旧 LLMClient）
│   │   ├── anthropic_provider.py # AnthropicNativeProvider（原生 Messages API）
│   │   ├── response.py / thinking.py / errors.py / error_ui.py
│   ├── loop_policy.py  # LoopPolicy 可拓展
│   ├── pipeline.py     # RecoveryPipeline / ResultPipeline
│   ├── recovery/       # 失败恢复策略
│   ├── self_healing.py
│   └── interrupt.py / message.py / context.py / session.py / empty_response.py
├── gateway/        # 网关适配器（Webhook / 自定义平台接入）
│   ├── base.py         # GatewayAdapter ABC
│   ├── registry.py     # GatewayRegistry：set_inbound_handler + start_all/stop_all
│   └── webhook.py      # WebhookGateway 参考适配器（FastAPI/uvicorn）
├── hooks/          # HookRegistry（15+ 事件：agent.start/stop, llm.before/after_chat,
│                   #                tool.before/after_execute, context.compact, ...）
├── mcp/            # MCP 客户端（manager / config / tool / builtin servers）
├── memory/         # MemoryStore + HybridRecaller + SessionStore（SQLite WAL）
├── observability/  # Observer / metrics / audit / tracing（hooks 驱动）
├── plugins/        # 插件系统
│   ├── base.py         # Plugin ABC + PluginContext（20+ 扩展点 + 一组便捷注册方法）+ PluginSpec
│   ├── discovery.py    # PluginDiscovery（entry_points + 目录扫描，无副作用）
│   ├── manager.py      # PluginManager（Kahn 拓扑 + priority，activate_boot / activate_all）
│   └── builtin/        # 8 个内置插件（entry-points 动态发现，零硬编码）
│       ├── observability/  # 创建 Observer（priority=100，boot 阶段）
│       ├── skills/         # 加载 skill registry + 注入 system prompt
│       ├── mcp/            # 创建 MCPServerManager
│       ├── subagent/       # SubAgentManager + TodoManager
│       ├── web/            # 注册 web fetch/search 工具
│       ├── gateway/        # 注册 WebhookGateway
│       ├── scheduler/      # 创建 CronScheduler
│       └── superpower/     # 扩展 superpower 能力
├── sandbox/        # ToolGuard / SecurityChecker / Confirm / Snapshot
├── scheduler/      # CronScheduler + jobs / delivery
├── skills/         # SkillLoader + SkillRegistry + 内置 SKILL.md
├── todo/           # TodoManager + TodoItem
├── tools/          # Bash / File / Web / MCP / Skill / Task / Edit / Middleware
├── utils/          # 通用工具函数
└── setup.py        # 交互式 setup 向导
```

---

## 🗂️ REPL 命令

> 命令分组（注册在 `cli/commands.py`，使用 `@cmd_registry.register(..., group=...)` 装饰器）。

| 组 | 命令 | 说明 |
|----|------|------|
| **info** | `/help` | 显示帮助 |
|  | `/model` | 显示当前模型 |
|  | `/context` | 上下文用量（进度条 + token 数 + 阈值/实测标记） |
|  | `/tools` | 列出可用工具（按 builtin / `mcp:<server>` 分组） |
|  | `/report` | 会话统计报告（token / LLM 延迟 / 工具分布 / 累计计数）；`/report reset` 清零 |
|  | `/reload-mcp` | 重新加载 MCP 服务器 |
|  | `/mcp-status` | MCP 服务器状态（已连接/工具数） |
| **session** | `/new` | 开启新会话 |
|  | `/sessions` | 历史会话列表；`/sessions <n>` 切换第 n 个 |
|  | `/fork` | 从当前会话创建分支 |
|  | `/tree` | 查看会话分支树（父子会话） |
|  | `/history` | 查看当前会话完整消息记录（支持 `/history <offset> <limit>` 分页） |
|  | `/revert` | 撤销本会话的文件修改（snapshot 回滚 + 确认） |
| **search** | `/search` | 在历史消息中搜索关键词 |
|  | `/recall` | 从历史会话中召回相关内容（HybridRecaller） |
| **memory** | `/remember` | 存一条记忆（支持 `/remember key=<k> <text>`） |
|  | `/memories` | 列出所有记忆；`/memories [tag]` 可按 tag 过滤 |
|  | `/forget` | 删除一条记忆（`/forget <key>`） |
| **system** | `/plugins` | 列出已安装插件（状态：已激活 / 未激活 / 已禁用 + 版本） |
| **task** | `/todos` | 列出所有任务（支持按 status 过滤） |
|  | `/todo` | 查看任务详情（`/todo <id>`） |
|  | `/todo-done` | 标记任务完成（`/todo-done <id>`） |
|  | `/agents` | 列出所有 AgentProfile |
|  | `/agent` | 查看 AgentProfile 详情（`/agent <name>`） |
| **control** | `/exit` `/quit` `/q` | 退出 REPL（自动保存 session + observer snapshot） |

> **未在此处列出命令的扩展点**：插件可通过 `PluginContext.add_processor("result_pipeline", ...)`、`add_memory_backend(...)`、`add_security_policy(...)` 等扩展点深度接入；CLI 命令注册也是开放扩展点。

---

## ⚙️ 配置示例

`merco.json`（常用字段示例；完整字段见 [`merco/core/config.py`](merco/core/config.py) 的 `MercoConfig`）：

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
    "recall_max_chars": 300,
    "auto_extract_on_session_end": false,
    "extract_max_per_session": 3,
    "extract_min_messages": 5
  },

  "session": {
    "fork_enabled": true,
    "fork_auto_on_compress": true,
    "fork_reset_observer": false
  },

  "sandbox_mode": "ask",
  "sandbox_rules": [],
  "diff_view": "unified",

  "mcp_servers": {},
  "plugins": {},

  "log_level": "INFO"
}
```

> **模型字段说明**：
> - `provider` —— `openai`（走 OpenAI 兼容协议，可填 `base_url` 接 DeepSeek / OpenRouter / 任何 OAI-兼容端点），或 `anthropic`（原生 Messages API）
> - `api_key` —— 不填时由 `ModelRegistry.select()` 兜底从环境变量读取（provider 指定的 `key_env` → `config.api_key`）
> - `fallbacks` —— 主 provider 失败时按 `ModelFallbackRecovery` 顺序尝试的备用 `ModelConfig` 列表

> **最小可行配置** —— 只需要 `model.provider` + `model.model` + `model.api_key`（或环境变量 `OPENAI_API_KEY` / `OPENROUTER_API_KEY`），其余字段均有合理默认值，`streaming` 子对象亦可省略。

---

## 🏗️ 架构状态

> 模块状态对齐 `docs/project-vision/references/architecture.md`。

| 模块 | 状态 | 说明 |
|------|:---:|------|
| Agent Loop | 🟢 POLISHED | `merco/core/agent.py` turn-loop + 工具调用调度，完整实现 |
| Tools | 🟢 POLISHED | Bash / File / Edit / Web / MCP / Skill / Task 等工具集 |
| Skills | 🟢 POLISHED | SkillLoader + SkillRegistry，自动注入到 system prompt |
| MCP | 🟢 POLISHED | `MCPServerManager` + `MCPPlugin` 完整实现（`/reload-mcp` / `/mcp-status`） |
| Memory | 🟢 POLISHED | Save（Strategy + Pipeline + Hook 三模式）+ Recall（HybridRecaller：FTS5 + JSON）双向闭环 |
| Context | 🟢 NEW | `ContextPipeline` + `CompressProcessor` + `CacheOptimizeProcessor` |
| Hooks | 🟢 POLISHED | `HookRegistry`，15+ 事件类型，全链路接入 |
| Sandbox | 🟢 POLISHED | `ToolGuard` 规则链 + `SecurityChecker` + `Confirm` UI + `Snapshot` 回滚 |
| Observability | 🟢 POLISHED | `Observer`（订阅 7+ 事件）+ MetricsCollector + AuditLogger + TracingSpan |
| Scheduler | 🟢 POLISHED | `CronScheduler` + `SchedulerPlugin`，通过 `AgentRuntime` 后台启动 |
| Plugins | 🟢 NEW | `Plugin` + `PluginSpec` + `PluginContext`（20+ 扩展点 + 一组便捷注册方法）+ `PluginDiscovery`（entry-points + 目录扫描）+ `PluginManager`（拓扑 + priority）；**8 个内置插件全部 entry-points 动态发现** |
| SubAgent | 🟢 NEW | `SubAgentManager` + `AgentProfile` + `AgentProfileRegistry` |
| Todo | 🟢 NEW | `TodoItem` + `TodoManager`，支持子任务分解 |
| Gateway | 🟢 NEW | `GatewayAdapter` ABC + `GatewayRegistry`（per-adapter 失败隔离）+ `WebhookGateway` 参考适配器（FastAPI/uvicorn，`port=0` OS 自动分配）；`GatewayPlugin`（priority=25）注册；`AgentRuntime` 统一生命周期宿主 |
| Utils | ⚪ UTIL | 通用工具函数 |
| **代码质量** | 🟢 | **ruff check 0 / ruff format 干净 / pre-commit `uv run ruff` 钩子 / 999 tests passed / 0 skipped / 0 failures** |

---

## 🔌 插件生态

### 8 个内置插件（entry-points `merco.plugins` 自动发现）

> 加载顺序由 `Plugin.priority` 决定 —— **越大越早激活**；`priority >= 100`（`BOOT_PRIORITY`）的插件在 boot 阶段早于 agent 装配前激活，其余按拓扑序在 `Agent.create` 时激活。

| 插件 | priority | 模式 | 说明 |
|------|:--:|:--:|------|
| **ObservabilityPlugin** | **100** | BOOT | 创建 `Observer` 并挂到 `PluginContext.observer`，必须在 agent 装配前就位 |
| **SkillsPlugin** | 60 | normal | 从 `skills_paths` 加载 SKILL.md，创建 `SkillRegistry` 注入 `ctx.skill_registry` |
| **MCPPlugin** | 50 | normal | 创建 `MCPServerManager`，启动时按 `mcp_servers` 自动连接 |
| **SubAgentPlugin** | 40 | normal | 创建 `SubAgentManager` + `TodoManager`，支持子 Agent 派发与任务分解 |
| **WebPlugin** | 30 | normal | 注册 `web_fetch` / `web_search` 工具 |
| **GatewayPlugin** | 25 | normal | 在 `ctx.gateway_registry` 注册内置 `WebhookGateway` |
| **SchedulerPlugin** | 20 | normal | 创建 `CronScheduler`，由 `AgentRuntime.start()` 后台 `asyncio.create_task` 拉起 |
| **SuperpowerPlugin** | 10 | normal | 扩展 superpower 能力（订阅 `agent.start` / `tool.error` 等事件，注入错误恢复 / 续命逻辑） |

### 插件接口

```python
from merco.plugins.base import Plugin, PluginContext

class MyPlugin(Plugin):
    name = "my_plugin"
    version = "1.0.0"
    description = "One-line description"
    priority = 50
    depends_on: list[str] = []  # 必须先激活的插件名

    async def activate(self, ctx: PluginContext) -> None:
        # 通过 ctx 访问全部子系统
        ctx.hooks.on("agent.start", self._on_start)
        ctx.register_tool(MyCustomTool())        # 便捷方法
        ctx.add_processor("result_pipeline", X()) # 便捷方法(白名单管线)

    async def deactivate(self) -> None:
        pass
```

### `PluginContext` 扩展点

> 经 `merco.plugins.base.PluginContext` 注入 `Plugin.activate(ctx)`，代码层直接读 subsystem 引用；同时支持 hook 事件订阅。

**属性（23 个，`PluginContext.__init__` 注入）**：`hooks` / `agent` / `config` / `tool_registry` / `skill_registry` / `prompt_builder` / `observer` / `scheduler` / `mcp_manager` / `todo_manager` / `sub_agent_manager` / `memory_save_pipeline` / `recaller` / `context_pipeline` / `agent_profiles` / `memory_backends` / `loop_policies` / `recovery_pipeline` / `result_pipeline` / `security_pipeline` / `model_registry` / `gateway_registry` / `metadata`。

**便捷注册方法（覆盖典型扩展场景）**：
- 事件订阅 / 工具 / 提示词 / 管线：`on(event, handler)` / `register_tool(tool)` / `add_prompt_chunk(chunk)` / `add_processor(pipeline_name, processor)` / `add_recaller(recaller)`
- 注册器类（拓展点）：`register_agent_profile(profile)` / `register_loop_policy(policy)` / `add_memory_backend(backend)` / `add_security_policy(policy)`
- 第三方接入：`register_model_provider(info)` / `register_gateway(adapter)`

### 三方插件安装方式

| 方式 | 配置 |
|------|------|
| **entry-point（推荐）** | 在你的 `pyproject.toml` 写 `[project.entry-points."merco.plugins"]`，merco 安装即被自动发现 |
| **目录扫描** | 在 `~/.config/merco/plugins/<name>/plugin.toml` 配 `entry = "module:Class"`，运行时被发现 |
| **`config.plugins`** | 用 `merco.json` 的 `plugins` 字段切 `enabled` / 传自定义 config；目录扫描同名覆盖 entry-points |

### 写一个第三方 ModelProvider

```python
from merco.core.llm.base import ModelProvider, ModelProviderInfo

class MyProvider(ModelProvider):
    name = "myprovider"

    async def chat(self, messages, **kw): ...
    async def chat_stream(self, messages, **kw): ...

# 在插件的 activate(ctx) 里：
ctx.register_model_provider(ModelProviderInfo(
    name="myprovider",
    provider_class=MyProvider,
    display_name="My Provider",
    base_url="https://api.example.com/v1",
    key_env="MYPROVIDER_API_KEY",
    default_model="my-model-1",
))
```

### 写一个第三方 GatewayAdapter

```python
from merco.gateway.base import GatewayAdapter

class TelegramGateway(GatewayAdapter):
    name = "telegram"

    async def start(self): ...
    async def stop(self): ...
    async def send_message(self, chat_id, message): ...

# 在插件的 activate(ctx) 里：
ctx.register_gateway(TelegramGateway(...))
# AgentRuntime.start() 会自动 set_inbound_handler + start_all
```

---

## 📡 Gateway 适配器（简表）

> 网关层接口对齐 `merco/gateway/{base,registry,webhook}.py`。

| 概念 | 角色 |
|------|------|
| `GatewayAdapter` | ABC（`name` / `start` / `stop` / `send_message` + `set_message_handler`），单个平台适配 |
| `GatewayRegistry` | 注册表 + 生命周期：`register` 重名 raise，`get` miss raise，`start_all` / `stop_all` per-adapter 失败隔离；`_name=name` 默认参防晚绑定 |
| `WebhookGateway` | FastAPI/uvicorn 参考适配器，`port=0` OS 自动分配，POST `/message` 收 `{chat_id, message}` → `{reply}`；可选 `outbound_url` 用于出站 |
| `GatewayPlugin` | 第 8 个内置插件，priority=25；`activate()` 时在 `ctx.gateway_registry` 注册内置 `WebhookGateway` |
| `AgentRuntime` | 统一生命周期宿主：`start()` 绑 `set_inbound_handler` + `start_all()`；`stop()` 幂等收尾；`handle_inbound(source, chat_id, message) → agent.run(message)` |

> **单 session 简化**：`handle_inbound` 当前直接 `agent.run(message)`，`chat_id` 保留前向兼容但不启用 per-chat_id 隔离（详见 spec §6）。

---

## 📖 项目文档

- 详细进展、架构决策、经验教训见 [docs/project-vision/](docs/project-vision/)
- 模块状态总览见 [docs/project-vision/references/architecture.md](docs/project-vision/references/architecture.md)
- 参考实现见 [`references/`](references/) 目录（Hermes Agent / OpenClaw / OpenCode，git 忽略）

## 🧪 测试 & 质量

```bash
# 跑全部测试（999 个用例）
uv run pytest

# 静态检查
ruff check .
ruff format --check .

# 提交前自动执行（.pre-commit-config.yaml 已配置）
pre-commit run --all-files
```

当前状态：**`999 tests passed / 0 skipped / 0 failures`**、ruff=0、format 干净、pre-commit 强制。

## 📄 许可证

MIT
