---
name: merco
description: Mercury Code (merco) agent operation guide — architecture, slash commands, tool usage, session management, configuration, file locations, sandbox rules, debugging. Use this when working on merco itself or needing to understand how merco works.
---

# Mercury Code (merco) 操作手册

你是 merco 的 assistant 角色，你可以使用工具执行操作、查询信息。

## 文件位置

```
./merco.json                     # 项目配置（优先级最高，不入库）
./.merco/merco.json              # 项目配置（备选位置）
~/.config/merco/config.json      # 全局用户配置
./.merco/sessions.db             # 会话数据库（SQLite）
~/.merco/sessions.db             # 全局会话数据库（fallback）
~/.merco/memory/                 # 记忆存储（JSON 文件）
./.merco/skills/                 # 项目本地技能
~/.config/merco/skills/          # 全局技能
config/merco.json.example        # 配置模板（git 跟踪，供参考）
```

## 架构概述

```
用户 ─→ CLI (prompt_toolkit) ─→ AgentRuntime (薄宿主, start/stop/submit/handle_inbound)
                                          │
                                          ├── Agent Loop (turn-loop)
                                          │     ├── _build_system_prompt (PromptBuilder)
                                          │     ├── LLM Chat via ModelProvider (OpenAICompatible / AnthropicNative, ModelRegistry.select())
                                          │     ├── _dispatch_tool_calls → _execute_tool_calls
                                          │     │        ├── ToolGuard.check() 守卫
                                          │     │        │     ├── SecurityChecker 正则硬拦截
                                          │     │        │     └── Guard 规则链 ask/deny/allow (28 条默认 ask 规则)
                                          │     │        └── ToolRegistry.execute()
                                          │     └── context.add → session.save (SQLite)
                                          ├── GatewayRegistry (start_all/stop_all, per-adapter 失败隔离)
                                          │     ├── WebhookGateway (FastAPI/uvicorn, port=0)
                                          │     └── (第三方注册的 GatewayAdapter, e.g. Telegram/Discord)
                                          └── CronScheduler (asyncio.create_task 后台跑)
```

**关键组件：**
- `AgentRuntime` (`merco/core/runtime.py`, ~116 行) — 生命周期宿主：owns Agent + CronScheduler + GatewayRegistry；`start()/stop()` 幂等；`submit(prompt)` 给 cron；`handle_inbound(source, chat_id, message)` 给 gateway inbound。
- `ContextManager` — 上下文窗口（滑动窗口 + 压缩）
- `Session` → `SessionStore` — SQLite 持久化（`sessions` + `messages` 表，WAL 模式）
- `ModelProvider` ABC + `ModelRegistry` — 多模型接入（OpenAICompatible + AnthropicNative），`select()` 独占凭证解析
- `Observer` — 可观察性：token 计数、工具调用统计、`/report` 报告
- `RecoveryPipeline` — LLM 错误恢复（重试/上下文压缩/切换模型）
- `ToolGuard` + `SecurityChecker` — 双层安全（SecurityChecker 正则硬拦截 + Guard 28 条默认 ask 规则）
- `MCPServerManager` — MCP 客户端（stdio + HTTP 传输，工具发现，自动注册）
- `InterruptCleanupPipeline` — Ctrl+C 中断清理（注入消息/终止进程/关闭 MCP/save 状态）
- `MemoryRecall` (HybridRecaller) — FTS5 全文搜索 + Memory JSON 文件双通道召回
- **插件系统（8 个内置插件，经 entry_points 动态发现）**：`ObservabilityPlugin`(100, BOOT) / `SkillsPlugin`(60) / `MCPPlugin`(50) / `SubAgentPlugin`(40) / `WebPlugin`(30) / `GatewayPlugin`(25) / `SchedulerPlugin`(20) / `SuperpowerPlugin`(10)。`PluginContext` 注入 **23 属性 + 11 便捷方法**（含 `model_registry` + `register_model_provider` + `gateway_registry` + `register_gateway`）。

## 配置

### 配置文件搜索顺序
调用 `MercoConfig.load()` 时按以下顺序查找，取第一个存在的：
1. `./merco.json`（项目根目录，优先级最高）
2. `./.merco/merco.json`（备选位置）
3. `~/.config/merco/config.json`（全局配置）

### 关键配置项
```json
{
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
  "username": "user",
  "streaming": {
    "enabled": false,
    "think": true,
    "content": true,
    "think_transient": false,
    "render_interval": 0.05
  },
  "max_input_tokens": 64000,
  "max_tool_calls": 50,
  "compression_threshold": 0.75,
  "sandbox_mode": "ask",
  "sandbox_rules": [
    {"tool": "bash", "pattern": "DROP TABLE", "action": "deny"}
  ],
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
  "skills_paths": ["./.merco/skills", "~/.config/merco/skills"],
  "plugins_paths": ["./.merco/plugins", "~/.config/merco/plugins"],
  "mcp_servers": {},
  "plugins": {},
  "session": {
    "fork_enabled": true,
    "fork_auto_on_compress": true,
    "fork_reset_observer": false
  }
}
```

### ModelConfig 字段
- `provider` — 形如 "openai"、"deepseek"、"minimax"（仅用于 setup 向导，不影响实际 API）
- `api_key` — API 密钥
- `base_url` — API 端点 URL（决定了实际调用哪个服务）
- `extra_params` — 额外传给 API 的参数（如 `top_p`、`seed`）。**若要流式返回 usage（Groq/Together 等需要），加 `"stream_options": {"include_usage": true}`**。**不要给不支持此参数的 API 加，否则 400。**
- `headers` — 自定义 HTTP header（如 `X-Title`）

## 可用的斜杠命令

> 27 个注册命令，6 个分组（info / session / search / memory / task / system / control）。详细列表见 [README §REPL 命令](../../README.md#-repl-命令)。

### 信息查询
| 命令 | 功能 |
|------|------|
| `/help` | 显示全部命令帮助 |
| `/model` | 当前模型 (provider/model) |
| `/tools` | 列出可用工具（按 builtin / `mcp:<server>` 分组） |
| `/context` | 上下文窗口用量 (current/max tokens) |
| `/report` | 会话统计：LLM 调用/工具调用/token 用量/缓存命中率；`/report reset` 清零 |
| `/reload-mcp` | 重新加载 MCP 服务器 |
| `/mcp-status` | MCP 服务器连接状态（已连接/工具数） |

### 会话管理
| 命令 | 功能 |
|------|------|
| `/new` | 创建新会话（当前自动 save） |
| `/sessions [n]` | 列出最近 n 个历史会话；`/sessions <n>` 切换第 n 个 |
| `/fork [title]` | 从当前会话创建分支 |
| `/tree` | 查看当前会话分支树（父子会话） |
| `/history [n]` | 查看当前会话完整消息记录 (分页) |
| `/revert` | 撤销本会话的文件修改 |

### 搜索
| 命令 | 功能 |
|------|------|
| `/search <关键词>` | 搜索所有历史消息 (FTS5 全文检索) |
| `/recall <关键词>` | 从历史会话中召回相关内容 (HybridRecaller) |

### 记忆
| 命令 | 功能 |
|------|------|
| `/remember` | 存一条记忆（`/remember key=<k> <text>`） |
| `/memories` | 列出所有记忆；`/memories [tag]` 可按 tag 过滤 |
| `/forget` | 删除一条记忆（`/forget <key>`） |

### 任务
| 命令 | 功能 |
|------|------|
| `/todos` | 列出所有任务（支持按 status 过滤） |
| `/todo <id>` | 查看任务详情 |
| `/todo-done <id>` | 标记任务完成 |
| `/agents` | 列出所有 AgentProfile |
| `/agent <name>` | 查看 AgentProfile 详情 |

### 系统
| 命令 | 功能 |
|------|------|
| `/plugins` | 列出已安装插件（状态：已激活 / 未激活 / 已禁用 + 版本） |

### 控制
| 命令 | 功能 |
|------|------|
| `/exit` `/quit` `/q` | 退出 REPL（自动保存 session + observer snapshot） |

## 可用工具

你有以下工具：

### BashTool (`bash`)
执行 bash 命令。

**守卫规则**（双层，自动执行，你无法绕过）：
- **SecurityChecker 硬拦截**（正则，不可绕过）：
  `rm -rf /`、`mkfs`、`dd if=`、`> /dev/sd`、`chmod 777 /`、`curl|bash`、`wget|bash`
- **Guard 规则链 ask**（弹出确认提示）：
  `rm`、`sudo`、`pip install/uninstall`、`npm -g`、`apt/yum/brew`、`git push`、`git reset --hard`、`shutdown`、`reboot`、`docker rm/rmi` 等 28 条默认规则
- **mode=auto**：完全跳过所有检查

### 文件工具
- **read_file** — 读取文件，支持 max_lines/head/tail，默认 500 行
- **write_file** — 新建文件。**不要用于修改已有文件**（用 edit_file）
- **edit_file** — SEARCH/REPLACE 修改已有文件，修改前展示 diff 并请求确认

**路径限制**（SecurityChecker.check_file_path）：
- 拦截 `/proc/*`、`/sys/*` 系统路径
- 拦截 `..` 路径穿越

### WebFetch
抓取网页内容 (httpx + HTML strip)。

### MCP 工具
- **mcp_call** — 调用已连接的 MCP 服务器工具
- 使用 `/mcp-status` 查看连接状态和已注册工具列表
- 使用 `/reload-mcp` 重新连接所有 MCP 服务器

### Skill 工具
- **skill_view** — 加载并查看技能文档内容

## 插件系统（8 个内置插件）

merco 插件经 `pyproject.toml` 的 `[project.entry-points."merco.plugins"]` 动态发现，agent.py 零硬编码 import。

| 插件 | priority | 职责 |
|------|:--:|------|
| `ObservabilityPlugin` | 100 (BOOT) | 创建 Observer，挂到 `PluginContext.observer` |
| `SkillsPlugin` | 60 | 从 `skills_paths` 加载 SKILL.md |
| `MCPPlugin` | 50 | 创建 `MCPServerManager`，启动时按 `mcp_servers` 自动连接 |
| `SubAgentPlugin` | 40 | `SubAgentManager` + `TodoManager` |
| `WebPlugin` | 30 | 注册 `web_fetch` / `web_search` 工具 |
| `GatewayPlugin` | 25 | 在 `ctx.gateway_registry` 注册内置 `WebhookGateway` |
| `SchedulerPlugin` | 20 | 创建 `CronScheduler`，由 `AgentRuntime.start()` 后台启动 |
| `SuperpowerPlugin` | 10 | 订阅 `agent.start` / `tool.error` 注入错误恢复 / 续命逻辑 |

**PluginContext**：23 注入属性 + 11 便捷方法。第三方扩展点：
- `ctx.register_model_provider(info)` — 注入自定义 `ModelProvider`（波2）
- `ctx.register_gateway(adapter)` — 注入自定义 `GatewayAdapter`（波3）
- `ctx.register_agent_profile(profile)` / `ctx.register_loop_policy(policy)` / `ctx.add_memory_backend(backend)` / `ctx.add_security_policy(policy)` — 注册器类扩展点
- `ctx.add_processor("result_pipeline", x)` / `ctx.add_recaller(r)` — 管线注入
- `ctx.on(event, handler)` / `ctx.register_tool(tool)` / `ctx.add_prompt_chunk(chunk)` — 基础便捷方法

**安装第三方插件**：写一个含 `plugin.toml` 的目录（`entry = "module:Class"`），丢到 `./.merco/plugins/<name>/` 或 `~/.config/merco/plugins/<name>/` 即可被 `PluginDiscovery` 发现。或在你的 `pyproject.toml` 注册 entry-point。

## Gateway 适配器

`AgentRuntime.handle_inbound(source, chat_id, message)` 是 webhook/gateway 统一入口（**Wave 3 单 session 简化**：当前 `agent.run(message)`，`chat_id` 保留前向兼容**但不启用 per-chat_id 隔离**）。

内置 `WebhookGateway`（FastAPI/uvicorn，`port=0` OS 自动分配；POST `/message` 收 `{chat_id, message}` → `{reply}`）。

## 会话与上下文

### 会话持久化
- SQLite 数据库，WAL 模式
- `sessions` 表：id、title、created_at、updated_at、message_count、parent_id、metadata
- `messages` 表：id、session_id、role、content、tool_call_id、tool_calls、reasoning、timestamp
- 启动自动恢复上次会话 → `_restore_context()` 灌入 ContextManager
- 每轮增量写盘（`session.save()`）
- Ctrl+C 退出自动 save

### 上下文管理
- `max_input_tokens` 控制窗口上限
- 达阈值 (compression_threshold=0.75) 自动压缩：LLM 总结 + 保留尾轮
- 压缩前自动 fork 归档
- reasoning 不存储到 context（防泄漏），仅中断路径例外

### Observer 统计
- 两套计数器：`_acc_map`（持久化锚点）+ `_live`（实时会话）
- 上报公式：`acc + (live - last_merged)` 防重复计数
- `/report` 显示本次+累计统计

## 安全模型

```
SecurityChecker.check_command()  ← 正则硬拦截（rm -rf /、mkfs...）
         ↓ 未命中
Guard._check() 规则链            ← 用户配置 + 默认 ask 规则
         ↓ 未命中
执行
```

- SecurityChecker 不可绕过，在模式匹配之前执行
- Guard 支持 `mode=auto` 完全跳过
- Guard 规则可通过 `merco.json` 的 `sandbox_rules` 自定义
- File 工具通过 `SecurityChecker.check_file_path()` 做路径安全

## 项目开发规范

### 如果你需要修改 merco 源码

1. **core/ 代码禁提 provider 名** — 注释、变量名、逻辑中不写具体厂商名
2. **tool_calls 格式** — OpenAI 标准：`{id, type:"function", function:{name, arguments}}`
3. **通解不补丁** — 修 bug 必须覆盖所有同类场景，不单改一个文件
4. **根因优先** — 必须先找到根本原因再修，禁止 `except: pass` 掩盖
5. **同类全检** — 修一个文件必须同步改所有类似代码
6. **TDD** — `tests/` 下 999 个测试（`uv run pytest`），跑全部验证
7. **`uv sync` 安装依赖**，`.venv/` 为虚拟环境
8. **`merco --debug`** 启动调试模式，日志前缀定位模块
9. **pre-commit 强制** — 提交前自动跑 `uv run ruff check .` + `uv run ruff format --check .`（`.pre-commit-config.yaml`，本地 hook 与项目 venv 版本对齐防漂移）

### 模块位置
```
merco/core/       — 核心引擎 (agent、runtime、llm/{base,registry,openai_provider,anthropic_provider,...}、config、context、session、message、pipeline、recovery/、loop_policy)
merco/tools/      — 工具系统 (bash、file、edit、web、task、skill；mcp_tools stub 已删)
merco/mcp/        — MCP 客户端 (manager、config、tool)
merco/memory/     — 记忆系统 (store、recall、save_pipeline、session_store、search、session_search、backend、backends/)
merco/sandbox/    — 沙箱安全 (guard、security、confirm、snapshot；isolation/permissions 已删)
merco/observability/ — 可观察性 (metrics、audit、tracing、logger、observer)
merco/hooks/      — 钩子系统 (registry、lifecycle、tool_hooks、chat_hooks)
merco/skills/     — 技能加载 (loader、registry、builtin/)
merco/gateway/    — 消息网关 (base、registry、webhook；Wave 3 新增)
merco/scheduler/  — 定时任务 (cron；jobs/delivery 已删)
merco/plugins/    — 插件系统 (base、discovery、manager、builtin/ 8 个内置插件)
merco/agents/     — AgentProfile + SubAgentManager
merco/todo/       — TodoManager + TodoItem
cli/              — CLI 实现 (main、commands、input_driver、interrupt、registry)
web/              — Web 接口 (FastAPI app, PARTIAL — /chat "coming soon")
tests/            — 测试 (core、mcp、observability、cli、integration、unit、gateway)
```

## 调试

```bash
merco --debug              # DEBUG 级别全链路日志
merco -m Qwen3-235B-A22B   # 指定模型
```

关键日志前缀：
- `merco.llm` — API 请求/响应、tool_calls 解析、None 字段防护
- `merco.agent` — Agent 循环、工具调度、reasoning 处理、stream done
- `merco.guard` — ToolGuard 守卫检查
- `merco.mcp` — MCP 连接/工具注册
- `merco.context` — context.add reasoning 泄漏 WARNING
- `merco.session` — 会话 add_message/持久化

## 调试案例

### 案例 1: MiniMax 400 "function.arguments must be in JSON format" (2026-06-04)

**现象**：某些进程启动后首次流式 API 调用，MiniMax 返回 400，`message: "function.arguments must be in JSON format"`。同一请求再次运行可能正常。加 `--debug` 后稳定正常。

**三次误判**：
1. `json.loads → json.dumps` 往返导致 arguments 格式变化 → **已退还**
2. `stream_options: {"include_usage": true}` 硬编码导致不支持 provider 400 → **已退还**（现为 `OpenAICompatibleProvider` 流式内部细节，非配置驱动）
3. 会话恢复时 reasoning 泄漏到历史消息 → **不匹配证据**

**根因**：`httpx.AsyncClient` 在 `OpenAICompatibleProvider.__init__()`（同步）中通过 `AsyncOpenAI()` 构造，但异步连接池的初始化还未被事件循环调度过。首次 `chat.completions.create()` 调用时，httpx 内部状态未就绪，造成连接建立竞态——API 收到不完整的请求体。`asyncio.sleep(0)` 让出一次事件循环即可解决。

**为何是 heisenbug**：任何导致首次 API 调用前出现同步操作的行为（debug 日志写入、文件 IO、多余的 json.dumps）都会改变事件循环的调度时机，从而掩盖竞态窗口。`--debug` 模式的额外日志输出恰好提供了足够的 yield 点。

**最终方案**：
```python
# __init__
self._client_ready = False

# 新方法
async def _ensure_client_ready(self):
    if self._client_ready:
        return
    await asyncio.sleep(0)
    self._client_ready = True

# _request 顶部
await self._ensure_client_ready()
```

**教训**：
1. **`--debug` 改变行为的 bug 往往是异步调度问题**——不是日志级别本身的问题，而是日志导致的 IO 操作改变了事件循环顺序
2. **裸 `sleep(0)` 是补丁，应该提取为命名方法 + flag**——`_ensure_client_ready` 自解释、只跑一次、好扩展
3. **永远先找根因再修**——三次误判消耗大量时间，最终只是一个 event loop yield
4. **heisenbug 排查方法**：可以故意在不同位置插入 `time.sleep()` 或 `await asyncio.sleep(0)` 来缩小竞态窗口范围

### 案例 3: 流式思考内容泄漏 + 渐进退化 + 空回复 (2026-06-11)

**现象**：含 tool call 的 session 重启多次后：1) 思考内容（reasoning）泄漏到 content panel 显示；2) 模型回复越来越短，最终完全空回复（只有 "⏳ 思考中…" 不更新）。

**根因链**：

1. MiniMax 流式返回的 chunk 中 `delta.content` 可能含与 reasoning 相同的思考文本（带或不带 `<think>` 标签）
2. `ThinkingExtractor.extract_from_delta()` — 当 DirectFieldStrategy/ModelExtraStrategy 返回 `{"reasoning": "..."}` 但没有 `"content"` key 时，fallback 行 224 取 `delta.content` 原样塞进 result["content"]——**含思考文本**
3. 流式路径 `_parse_chunk` 缺 `_strip_think_tags` 清理（非流式 `_parse_response:409` 有）
4. 污染 content 存入 session → 重启后 `_restore_context` 加载回上下文 → 反馈给模型 → 模型退化

**修复**：三处加 `_strip_think_tags()`：
- `extract_from_delta` fallback（2 处：策略命中但无 content + 无策略命中）
- `_parse_chunk` content 提取（流式路径对齐非流式）

**教训**：流式和非流式路径的 content 处理必须一致。写完流式逻辑后必须搜索非流式的同类处理，检查是否漏了清理步骤。

### 案例 4: 压缩 checkpoint 过时导致记忆丢失 (2026-06-11)

**现象**：session 多轮对话后重启，模型不记得前面几轮的内容，但 `/history` 显示消息完整。

**根因**：`compress_checkpoint` 一次创建后永不过期。session 在 283 条消息时压缩，之后新增到 630 条——但每次重启只恢复旧 summary + 4 条旧 tail，中间 340+ 条消息全部丢失。

**修复**：
1. `_restore_context` 检测过时：`len(all_msgs) > original_count + 20` → 删除旧 checkpoint → 全量恢复 → 自动重新压缩
2. `tail_count` 从 2 提到 5（保留 10 条消息/5 轮对话）

### 案例 5: CompressCountRecovery 永不生效 (2026-06-11)

**现象**：LLM 返回 context-too-large 错误时，压缩恢复策略不触发，直接报"模型调用失败"。

**根因**：`RecoveryContext` dataclass 有 `max_compress` 字段但缺少 `compress_count` 字段。`ContextCompressRecovery.attempt()` 访问 `ctx.compress_count` 抛 AttributeError，被 `RecoveryPipeline.attempt()` 的 `except Exception` 吞掉。

**修复**：`RecoveryContext` 加 `compress_count: int = 0`；`RecoveryPipeline.attempt()` 在 `ctx.compress=True` 时递增。

### 案例 6: Thinking 提取策略链的边缘场景 (2026-06-13)

**现象**：某些模型同时使用 think 标签 + reasoning_content/reasoning 字段。

**架构**（`merco/core/llm.py`）：
```
API 返回的 chunk/message
    ├── content: "正文[^think]思考[/think]更多正文"
    ├── reasoning_content: "这是模型的思考"  ← 某些模型使用
    └── reasoning: "这是模型的思考"         ← 某些模型使用

策略链：
1. DirectFieldStrategy — 提取 reasoning_content/reasoning 字段
2. ModelExtraStrategy — 提取 model_extra 中的思考
3. ThinkTagStrategy — 提取 content 中的 <think>...[/think] 标签
```

**当前逻辑**：
```python
# ThinkingExtractor.extract_from_delta()
for s in self._strategies:
    result = s.extract_from_delta(delta)
    if result is not None:
        if "content" not in result:
            raw = getattr(delta, "content", None) or ""
            result["content"] = _strip_think_tags(raw)
        return result  # ← 首个命中直接返回
```

**边缘情况**：如果模型同时使用 think 标签 + reasoning 字段，两者的思考内容都会丢失（一个被策略消费，一个被 strip_think_tags 清理）。

**结论**：这是架构的遗漏不完善，不影响主流使用。大多数模型是二选一：
- DeepSeek/MiniMax → 用 reasoning_content/reasoning 字段
- Claude → 用 think 标签
- 同时使用的情况极少，可以后续完善策略合并逻辑。
