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
用户 ─→ CLI (prompt_toolkit) ─→ Agent Loop
                                     ├── _build_system_prompt (PromptBuilder)
                                     ├── LLM Chat (流式/非流式)
                                     ├── _dispatch_tool_calls → _execute_tool_calls
                                     │        ├── ToolGuard.check() 守卫
                                     │        │     ├── SecurityChecker 正则硬拦截
                                     │        │     └── Guard 规则链 ask/deny/allow
                                     │        └── ToolRegistry.execute()
                                     └── context.add → session.save (SQLite)
```

**关键组件：**
- `ContextManager` — 上下文窗口（滑动窗口 + 压缩）
- `Session` → `SessionStore` — SQLite 持久化（`sessions` + `messages` 表，WAL 模式）
- `Observer` — 可观察性：token 计数、工具调用统计、`/report` 报告
- `RecoveryPipeline` — LLM 错误恢复（重试/上下文压缩/切换模型）
- `ToolGuard` + `SecurityChecker` — 双层安全（SecurityChecker 正则硬拦截 + Guard 规则链）
- `MCPServerManager` — MCP 客户端（stdio + HTTP 传输，工具发现，自动注册）
- `InterruptCleanupPipeline` — Ctrl+C 中断清理（注入消息/终止进程/关闭 MCP/save 状态）
- `MemoryRecall` (HybridRecaller) — FTS5 全文搜索 + Memory JSON 文件双通道召回

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
    "api_key": "...",
    "base_url": "https://api.openai.com/v1",
    "temperature": 0.7,
    "max_tokens": 4096,
    "extra_params": {},
    "headers": {}
  },
  "username": "user",
  "streaming": true,
  "stream_thinking": true,
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
    "recall_enabled": true,
    "recall_limit": 3,
    "recall_max_chars": 300
  },
  "skills_paths": ["./.merco/skills", "~/.config/merco/skills"],
  "mcp_servers": {},
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

### 信息查询
| 命令 | 功能 |
|------|------|
| `/help` | 显示全部命令帮助 |
| `/model` | 当前模型 (provider/model) |
| `/tools` | 列出可用工具（`check()` 为 True 的才显示） |
| `/context` | 上下文窗口用量 (current/max tokens) |
| `/report` | 会话统计：LLM 调用/工具调用/token 用量/缓存命中率 |

### 会话管理
| 命令 | 功能 |
|------|------|
| `/new` | 创建新会话（当前自动 save） |
| `/sessions [n]` | 列出最近 n 个历史会话 |
| `/fork [title]` | 从当前会话创建分支 |
| `/tree` | 查看当前会话分支树 |
| `/history [n]` | 查看当前会话完整消息记录 (分页) |
| `/revert` | 撤销本会话的文件修改 |

### 搜索
| 命令 | 功能 |
|------|------|
| `/search <关键词>` | 搜索所有历史消息 (FTS5 全文检索) |
| `/recall <关键词>` | 从历史会话中召回相关内容 (HybridRecaller) |

### 控制
| 命令 | 功能 |
|------|------|
| `/exit` `/quit` `/q` | 退出 |
| `/reload-mcp` | 重新加载 MCP 服务器 |
| `/mcp-status` | 显示 MCP 服务器连接状态 |

## 可用工具

你有以下工具：

### BashTool (`bash`)
执行 bash 命令。

**守卫规则**（双层，自动执行，你无法绕过）：
- **SecurityChecker 硬拦截**（正则，不可绕过）：
  `rm -rf /`、`mkfs`、`dd if=`、`> /dev/sd`、`chmod 777 /`、`curl|bash`、`wget|bash`
- **Guard 规则链 ask**（弹出确认提示）：
  `rm`、`sudo`、`pip install/uninstall`、`npm -g`、`apt/yum/brew`、`git push`、`git reset --hard`、`shutdown`、`reboot`、`docker rm/rmi` 等 20+ 条
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
6. **TDD** — `tests/` 下 175+ 个测试，跑 `pytest tests/` 验证
7. **`uv sync` 安装依赖**，`.venv/` 为虚拟环境
8. **`merco --debug`** 启动调试模式，日志前缀定位模块

### 模块位置
```
merco/core/       — 核心引擎 (agent、llm、config、context、session、message、pipeline 等)
merco/tools/      — 工具系统 (bash、file、edit、web、task、mcp、skill)
merco/mcp/        — MCP 客户端 (manager、config、tool)
merco/memory/     — 记忆系统 (store、recall、compressor、search、session_store)
merco/sandbox/    — 沙箱安全 (guard、security、isolation、permissions、confirm)
merco/observability/ — 可观察性 (metrics、audit、tracing、logger、observer)
merco/hooks/      — 钩子系统
merco/skills/     — 技能加载
merco/gateway/    — 消息网关
merco/scheduler/  — 定时任务
cli/              — CLI 实现 (main、commands、input_driver、interrupt)
tests/            — 测试 (core、mcp、observability、cli、integration、unit)
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
2. `stream_options: {"include_usage": true}` 硬编码导致不支持 provider 400 → **已退还**（改为 ModelConfig 显式字段）
3. 会话恢复时 reasoning 泄漏到历史消息 → **不匹配证据**

**根因**：`httpx.AsyncClient` 在 `LLMClient.__init__()`（同步）中通过 `AsyncOpenAI()` 构造，但异步连接池的初始化还未被事件循环调度过。首次 `chat.completions.create()` 调用时，httpx 内部状态未就绪，造成连接建立竞态——API 收到不完整的请求体。`asyncio.sleep(0)` 让出一次事件循环即可解决。

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

### 案例 2: 上下文持久化 Bug（2026-06-04 定位 / 2026-06-05 部分修复）

#### 现象

1. **对完一轮对话后，上下文 token 数反降** — before 12000，after 8000
2. **退出重进，上下文 token 数骤减** — 与退出前差距可达 50%
3. **模型遗忘前面对话** — history、report 完整，但 LLM 输出显示不记得
4. **快速 Ctrl+C 退出后重进，聊天报错**：`<400> messages with role "tool" must be a response to a preceeding message with "tool_calls"`

#### 根因 1：进度条"反降"是 cache 命中导致口径切换

启动时进度条显示 17K（估算：估算公式 1.5 token/字 + 200 token/工具，**对中文偏估**），第一次 API 响应后覆盖成 6.7K（实测，含 cache 命中打折）。**估算 17K 不是 bug——merco 没 API 数据只能估算；6.7K 才是真实。**用户看到"反降"是事实不是 bug，但体验差。

**修法**（commit 57ccb83 + c137185）：第一次 API 响应前**显示占位** `—/62.5K` 而非估算值，避免误导。复用 `get_context_stats()` 已有的 `is_estimate` 字段；`_fmt` 加默认参数保持向后兼容。

**根因 A/B/C（last_actual_tokens 过期 + _overhead_tokens 未持久化）当前未修**：
- A/B 实际影响已被根因 1 修复屏蔽（进度条走估算口径时不再读 last_actual_tokens）
- C 影响窗口仅限"启动到第一次 run 之间"几秒，run 入口已有 set_overhead 补救
- 严格修需把 `_restore_context` 改 async，影响 6 处调用点，**当前不建议**

#### 根因 D：空 `tool_call_id` 被 falsy 过滤导致消息链断裂（2026-06-05 修复）

`agent.py:391, 404` — `_restore_context` 恢复消息时：

```python
if msg.get("tool_call_id"):              # "" 是 falsy → 跳过
    entry["tool_call_id"] = msg["tool_call_id"]
```

触发条件：provider（如 scnet.cn）流式首 chunk 不发送 `tool_call.id`，若 Ctrl+C 中断在 id 到达前，`StreamingProvider` 取消检查点保存的 `tc_buf[idx]["id"]` 为 `""` → 清理管线注入 `"取消 (Ctrl+C)"` tool 消息的 `tool_call_id` 也是 `""` → `session.save()` 写入 SQLite → 重启后 `""` 被过滤 → tool 消息无 `tool_call_id` → 下轮 API 调用报 400。

**修法**（commit 1ebd698）：两行 `if msg.get("tool_call_id"):` → `if "tool_call_id" in msg:` —— key 存在就赋值，不管真假。空串字段在重启后保留，消息链不断。

**未修方案**（按"只修 D"原则搁置）：
1. `context.py` `ContextManager.add()` 末尾 `self.last_actual_tokens = 0`（根因 A）
2. `agent.py` `_restore_context()` 末尾重建 `_overhead_tokens`（根因 C，需 async 化）

## 修复提交索引

- `c137185` fix(cli): 进度条估算态一律占位（根因 1，第二版修对）
- `57ccb83` fix(cli): 进度条首次 API 响应前显示占位（根因 1，第一版修错）
- `1ebd698` fix(agent): _restore_context 保留空 tool_call_id 字段（根因 D）
