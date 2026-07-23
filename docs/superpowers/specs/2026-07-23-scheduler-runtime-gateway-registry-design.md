# Wave 3 设计：Scheduler -> Runtime + GatewayRegistry

- **日期**: 2026-07-23
- **波次**: Wave 3（多入口）
- **状态**: 设计稿（待评审）
- **前置**: Wave 1（插件动态加载）✅、Wave 2（ModelProviderRegistry）✅
- **路线图依据**: `docs/project-vision/references/plugin-dynamic-loading-plan.md:55-59`（波3 = P4 + P5）、`plugin-roadmap.md:80-134`、`progress.md:250-286`

## 1. 目标与背景

用户总目标：**可动态拓展（插件系统）、架构清爽干净、不留历史债务**。

Wave 3 = 文档定义的 **P4 + P5**：
- **P4**：`CronScheduler` 已存在但**从未被启动**（`progress.md:250` 标 `NOT WIRED`）。`SchedulerPlugin` 把实例挂到 `PluginContext.scheduler`，但没有任何调用方（CLI/Web）调用 `start()`。把它接入一个活的 Runtime。
- **P5**：`GatewayAdapter` ABC + `GatewayRegistry` + 消息路由 + 多入口 Runtime。`merco/gateway/` 目前是 `pass` stub 骨架，`GatewayRegistry` 完全不存在。

P4 在 P5 前，因为 "Gateway 依赖一个活着的 Runtime 入口"。

## 2. 范围

**IN**：
- `AgentRuntime` 生命周期宿主（拥有 Agent + CronScheduler + GatewayRegistry，`start/stop/submit/handle_inbound`）
- CronScheduler 接入 Runtime 生命周期（真启动、job 真触发、路由到 agent）
- `GatewayAdapter` ABC（重命名自 `BaseGateway`）+ `GatewayRegistry`（register/get/list + `start_all/stop_all`）
- `WebhookGateway` 参考适配器（FastAPI/uvicorn，无外部凭据可测）—— 证明 ABC 不被形塑错（借鉴 Wave 2 Anthropic provider 教训）
- `PluginContext.gateway_registry` + `ctx.register_gateway(adapter)` 扩展点
- CLI 改造：用 Runtime 承载生命周期，REPL 本身不动
- 去债：删 `DeliveryManager`、删死代码 `TaskManager`、修 cron 解析器 stub + 异常吞掉、删 Telegram/Discord `pass` stub

**OUT**（文档明确排除，另开）：
- TUI、Web->Agent UI、SubAgent 多智能体协作
- agent.py 瘦身 / 主循环结构重构（独立关注点，见 §10）
- 统一所有 7 个 registry 的 `get()` 语义（orthogonal 一致性重构）

## 3. 架构总览

```
   ┌──────────────── 入口层 (entries) ────────────────┐
   │  CLI REPL     GatewayAdapter(webhook)    Cron job │
   │     │              │  inbound                │    │
   │     │              ▼                         │    │
   │     │     POST {chat_id,msg}->{reply}        │    │
   │     │              │                         │    │
   └─────┼──────────────┼─────────────────────────┘    │
         ▼              ▼                              │
       ┌─── AgentRuntime (merco/core/runtime.py) ───┐  │
       │  owns: Agent · CronScheduler · GatewayReg  │◄─┘
       │  start()/stop()/submit()/handle_inbound()  │
       └───────┬──────────────────┬─────────────────┘
               ▼                  ▼
         CronScheduler      GatewayRegistry
         start/stop          start_all/stop_all
                                  │
                            GatewayAdapter ABC
                            └─ WebhookGateway (参考实现)
```

**一个 Runtime 统管** scheduler + gateway（文档里的 "GatewayRuntime"/"CronScheduler Runtime" 是路线图原子，不是两个类；统一更清爽）。所有入口最终都落到 `agent.run()`，**Runtime 不碰 turn-loop**。

## 4. 组件

### 4.1 `AgentRuntime`（`merco/core/runtime.py`，新）

生命周期宿主。不继承任何插件基类，是 core 层组件，由 CLI 构造。

```python
class AgentRuntime:
    def __init__(self, config: MercoConfig, *, tool_registry=None, agent: Agent | None = None): ...

    @property
    def agent(self) -> Agent: ...          # 懒解析；若未传入则 start() 时 Agent.create()

    async def start(self) -> None:
        # 1. 若 agent 未传入：self._agent = await Agent.create(self.config, self._tool_registry)
        #    （触发插件两阶段激活：activate_boot -> restore -> activate_all）
        #    激活后 ctx.scheduler（SchedulerPlugin 提供）与 ctx.gateway_registry（GatewayPlugin 注册内置 + 第三方）已就位
        # 2. ctx = agent.plugin_ctx（Agent 新增 @property，见 §12）；读：
        #    self.scheduler = ctx.scheduler; self.gateway_registry = ctx.gateway_registry
        # 3. self.gateway_registry.set_inbound_handler(self.handle_inbound)
        # 4. await self.gateway_registry.start_all()   # 先绑 handler 再 start
        # 5. await self.scheduler.start()
        # 幂等：if self._started: return

    async def stop(self) -> None:
        # 1. await gateway_registry.stop_all()
        # 2. await self.scheduler.stop()
        # 3. agent 收尾（emit agent.stop hook 等）
        # 幂等

    async def submit(self, prompt: str) -> str:
        # 编程式 / cron job 入口 -> agent.run(prompt)

    async def handle_inbound(self, source: str, chat_id: str, message: str) -> str:
        # gateway 入口 -> agent.run(message) -> reply
        # chat_id 保留为前向兼容参数；Wave 3 单 session（见 §6），不做 per-chat_id 隔离
```

**关键不变量**：
- `start()/stop()` 幂等、可重入。
- 某 gateway `start()` 失败：记日志 + emit hook，不影响其他 gateway 和 scheduler（隔离）。
- `handle_inbound` 路由到 agent 默认 session（Wave 3 单 session，见 §6）；`chat_id` 保留前向兼容但不隔离。

### 4.2 `GatewayAdapter` ABC（`merco/gateway/base.py`，重命名自 `BaseGateway`）

传输层抽象。bidirectional（收 inbound + 发 outbound）。

```python
class GatewayAdapter(ABC):
    name: str
    def set_message_handler(self, handler: Callable[[str, str], Awaitable[str]]) -> None: ...
    async def start(self) -> None: ...      # 开始监听（如起 HTTP 服务）
    async def stop(self) -> None: ...       # 关闭
    async def send_message(self, chat_id: str, message: str) -> None: ...  # outbound
    # inbound：adapter 收到消息后回调 handler(chat_id, message) -> reply（async）
```

`set_message_handler` 由 `GatewayRegistry.start_all()` 绑定：每个 adapter 绑 `lambda cid, msg: runtime.handle_inbound(adapter.name, cid, msg)`。

### 4.3 `GatewayRegistry`（`merco/gateway/registry.py`，新）

仿 Wave 2 `ModelRegistry` 模式。**差异点：entries 是活的（需生命周期）**，故有 `start_all/stop_all`。

```python
class GatewayRegistry:
    def __init__(self): self._adapters = {}; self._inbound_handler = None
    def register(self, adapter: GatewayAdapter) -> None: ...   # name 唯一，重复 raise
    def get(self, name: str) -> GatewayAdapter: ...            # KeyError on miss（对齐 ModelRegistry）
    def list(self) -> list[GatewayAdapter]: ...
    def set_inbound_handler(self, handler) -> None: ...        # Runtime 在 start_all 前设
    async def start_all(self) -> None:   # 每个 adapter：set_message_handler(bound) -> adapter.start()
    async def stop_all(self) -> None:    # 每个 adapter：adapter.stop()
```

`get()` 语义选 **KeyError**（对齐最新的 ModelRegistry，而非多数派的 None-return）。`register()` **重复名 raise**（有意改进：`ModelRegistry.register` 是静默覆盖；此处"对齐 ModelRegistry"仅指 `get()`=KeyError，`register()` dup-raise 是有意 divergence）。其余 6 个 registry 的 `get()` 不一致是 pre-existing，**不在 Wave 3 改**（orthogonal，记为已知项）。

### 4.4 `WebhookGateway`（`merco/gateway/webhook.py`，新）—— 参考实现

用 **FastAPI + uvicorn**（均已是依赖）。`uvicorn` 此前声明未用、本波首次启用；`fastapi` 已被 `web/app.py` 使用。无新依赖。

```python
class WebhookGateway(GatewayAdapter):
    name = "webhook"
    def __init__(self, *, host="127.0.0.1", port=0, path="/message", outbound_url: str | None = None): ...
    def set_message_handler(self, handler): self._handler = handler
    async def start(self):  # 建 FastAPI app：POST path 收 {chat_id, message} -> await handler -> {reply}；起 uvicorn（port=0 = 随机空闲端口）；记录 actual_port
    async def stop(self):   # 停 uvicorn server
    async def send_message(self, chat_id, message):  # outbound_url 配了就 POST {chat_id, message}；没配 no-op + log
```

- 同步请求/响应模型：reply 直接走 HTTP 响应（`POST /message -> {reply}`）。
- `port=0` 让 OS 分配空闲端口，测试可读 `actual_port` 后 POST。
- `send_message` 满足 ABC 契约：配 `outbound_url` 时 POST 出站，否则 no-op（webhook 场景 reply 已在响应里）。

### 4.5 `SchedulerPlugin` 改造（`merco/plugins/builtin/scheduler/plugin.py`）

- **只负责提供实例**：`ctx.scheduler = CronScheduler()`（不变）。
- **不再管启动**：启动/停止是 Runtime 的职责（`Runtime.start()` 调 `ctx.scheduler.start()`）。这分离了 "provider"（插件）与 "lifecycle owner"（Runtime）。
- 插件可在 `activate()` 里 `ctx.scheduler.add_job(name, schedule, handler)` 注册内置 job；job handler 通过 `ctx.agent.run(...)` 路由到 agent（`agent` 已在 PluginContext 上）。

### 4.6 `GatewayRegistry` 容器归属 + `GatewayPlugin` + `PluginContext` 扩展

- **容器归属**：`GatewayRegistry` 容器由 Agent 构造并挂到 `ctx.gateway_registry`（仿 `ToolRegistry`/`LoopPolicyRegistry` 模式：Agent 构造容器、插件填充条目）。Runtime 从 ctx 读取并 `start_all/stop_all`。
- **内置网关**：新 `GatewayPlugin`（`merco/plugins/builtin/gateway/plugin.py`，仿 `SchedulerPlugin`/`WebPlugin`）注册内置 `WebhookGateway`。第三方网关经 `ctx.register_gateway(adapter)` 注册。Runtime 不硬编码网关，只 start 注册表里的。
- **PluginContext 扩展**（`merco/plugins/base.py`）：新增属性 `gateway_registry` + 便捷方法 `register_gateway(adapter)`（仿 `register_model_provider`，`base.py:151-155`）。

### 4.7 CLI 改造（`cli/main.py`）

**关键约束**：scheduler/gateway 是 async 长任务，必须与 REPL **同一事件循环**。当前 `main()` 用 `asyncio.run(_setup_agent)`（一次性 loop 构造 agent）+ `run_repl` 内 `asyncio.run(repl())`（另一个 loop）—— **两套 loop**。Runtime 改造必须把 agent 构造 + 生命周期并入 REPL 的长生命周期 loop。

- `_setup_agent` -> 改为返回 `(AgentRuntime 未启动, config_source)`（构造 Runtime，**不 start**、也不 `Agent.create`--那移入 `runtime.start()`）。dashboard 构造依赖 agent，移入 `repl()`。
- `run_repl(runtime, ...)`：在 `repl()` 协程内 `await runtime.start()`（与 REPL 同 loop，内含 `Agent.create` + 插件激活 + scheduler/gateway 启动）-> dashboard 构造 -> REPL 循环（**不变**，继续直连 `runtime.agent`）-> `finally: await runtime.stop()`。
- 信号处理（SIGINT/SIGTERM，`:462-525`）保留，stop 时确保 `runtime.stop()`。
- REPL 的流式/中断/todo 显示逻辑**不动**——Runtime 不复制 REPL 的丰富逻辑，只包生命周期。

## 5. 数据流

- **CLI**：用户输入 -> REPL（不变）-> `agent.run`。Runtime 只管 REPL 前后的 scheduler/gateway 生命周期。
- **Gateway inbound**：webhook 收 `POST /message {chat_id, message}` -> adapter 调 `handler(chat_id, msg)` -> `runtime.handle_inbound("webhook", chat_id, msg)` -> `agent.run(msg)` -> reply -> HTTP 响应 `{reply}`（Wave 3 单 session，见 §6）。
- **Cron job**：scheduler 触发 -> job handler（闭包持 ctx）-> `ctx.agent.run(...)`（或 `runtime.submit`）-> agent.run。

## 6. Session 路由（P5 消息路由）-- Wave 3 单 session

`runtime.handle_inbound(source, chat_id, message)` -> `agent.run(message)` -> reply。

**Wave 3 范围：单 session。** Agent 当前是单 session 架构（`agent.session` 在 `__init__` 一次性设定，`agent.run(prompt)` 无 session_id 参数）。per-chat_id session 隔离需要 agent 侧多 session 支持（session+context 切换），是对已验证核心的较大改动，且 Wave 3 网关是参考 webhook 适配器（单用户测试场景），非生产多用户网关。

按 YAGNI + 不留债：Wave 3 `handle_inbound` 路由到 agent 默认 session；`chat_id` 参数保留为前向兼容（签名稳定），但**不做** per-chat_id 隔离，也**不留**半成品 `_sessions` map stub。per-chat_id 隔离明确列为 OUT，待首个真实多用户网关（Telegram/Discord 插件）落地时连同 agent 侧多 session 支持一起做。

## 7. 去债（一并清理，不留并行结构）

| 项 | 处置 | 位置 |
|---|---|---|
| `DeliveryManager`（telegram/discord/email 频道注册，与 gateway 概念重复） | **删**，概念并入 GatewayRegistry | `merco/scheduler/delivery.py` |
| `TaskManager`（死代码，无调用方） | **删** | `merco/scheduler/jobs.py` |
| cron `_run_job` `except Exception: pass` 吞异常 | **修**：记日志 + emit hook，不吞 job 异常 | `merco/scheduler/cron.py:75-76` |
| cron `_is_due` 解析器：weekday 用错约定（Mon=0，cron 应 Sun=0）+ 无 ranges/lists/steps | **修**：weekday 改 Sun=0 约定 + 诚实 docstring（明示仅支持 `*` 与精确值，不支持 ranges/lists/steps）；完整 cron 支持或引入库 = OUT（YAGNI） | `merco/scheduler/cron.py:78-100` |
| `BaseGateway` 命名 | **重命名** -> `GatewayAdapter`（对齐文档） | `merco/gateway/base.py` |
| `TelegramGateway`/`DiscordGateway`（`pass` stub） | **删** core 内 stub，改为插件提供 | `merco/gateway/telegram.py`、`discord.py` |

## 8. 错误处理

- gateway/job 抛错**不吞**：记日志 + emit hook（复用 `plugin.error`；视需要加 `gateway.error`），不 crash Runtime。
- `Runtime.start()/stop()` 幂等、可重入。
- 单个 gateway `start()` 失败隔离：不影响其他 gateway 和 scheduler。
- cron job 异常：`_run_job` 不再 `except: pass`，记日志 + hook，下一个 job 不受影响。

## 9. 测试策略

- **WebhookGateway**：`port=0` 起服务，读 `actual_port`，`httpx` `POST /message {chat_id, message}`，断言 `{reply}`。`send_message` 配/不配 `outbound_url` 两条路径。无外部依赖、无凭据。
- **GatewayRegistry**：`register`（含重复名 raise）/`get`（含 KeyError）/`list` + `start_all/stop_all` 生命周期顺序 + handler 绑定正确。
- **AgentRuntime**：`start/stop` 顺序与幂等、`handle_inbound` 路由到 `agent.run`（单 session，见 §6）、`submit`、单 gateway 失败隔离。
- **Scheduler wiring**：`runtime.start()` 后 CronScheduler 真启动；用极短间隔或手动 `_check_jobs()` 证 job 真触发并路由到 agent。
- **CLI**：`run_repl` 在单 loop 内 `start/stop` Runtime（不再两套 loop）；REPL 行为不回归。
- **去债验证**：grep 证实 `DeliveryManager`/`TaskManager`/`BaseGateway`/telegram.py/discord.py 全删；`pass` stub 零残留。

## 10. 循环可插拔性（明确边界，避免误解）

**Wave 3 与 agent 主循环的可插拔性正交。** 循环 `_agent_loop`（`agent.py:460`）作为**稳定核心**保持不动（文档决定 `plugin-extensibility-analysis.md:25`："核心调度器，不能被插件随意替换"）。

插件对循环的**行为级**可拓展（**已有，Wave 3 不改**）：
- 改 LLM 输入：`llm.before_chat` hook（`agent.py:478-481`）
- 短路/替换 LLM 调用：`llm.before_chat` 返回 `stop=True` + `data["response"]`（`agent.py:482-483`）
- 改写 LLM 输出：`llm.after_chat`（`agent.py:514-516`）
- 控制 continue/exit：自定义 `LoopPolicy` + `set_active()`（`agent.py:548`、`loop_policy.py`）
- 错误 recovery：recovery_pipeline（`agent.py:501`）
- tool 执行：`tool.*` hooks

插件**不能**改循环的**结构骨架**（阶段顺序、新增阶段、替换骨架）——这是有意的稳定核心设计，不是债务。若将来冒出"插件要插入新循环阶段"的具体需求，另开"可插拔循环"重构波次。

"插件可拓展"在两个轴上成立：循环行为（已有 hooks/policies/pipelines）+ 入口（本波 Runtime/GatewayRegistry）。

## 11. 已拒绝的替代方案

- **Runtime 接管 turn-loop**：高风险、混入 agent.py 拆分这个独立关注点 -> 拒。
- **core 内置真实 Telegram+Discord**：耦合外部 SDK、难测 -> 拒（改插件提供）。
- **只做 ABC+Registry 不带参考适配器**：抽象未被证明，重蹈 Wave 2 "ABC 被形塑错"风险 -> 拒。
- **结构级循环可插拔（Step/LoopStrategy）**：YAGNI、高风险碰核心、与多入口正交 -> 拒（留待将来按需开波）。
- **统一所有 7 个 registry 的 `get()` 语义**：orthogonal 一致性重构，超 Wave 3 范围 -> 不做（GatewayRegistry 对齐 ModelRegistry=KeyError，其余记已知项）。
- **两个 Runtime（GatewayRuntime + CronScheduler Runtime）**：路线图原子非实现要求，统一一个 Runtime 更清爽 -> 拒。

## 12. 计划期已决定的细节（plan-research 校正）

> 以下原为"留待确认"，经实现计划研究的代码核实已定：

- **ctx 访问**：Agent 新增 `@property def plugin_ctx(self) -> PluginContext: return self._plugin_ctx`（当前 `_plugin_ctx` 私有、无 accessor）。Runtime 读 `agent.plugin_ctx.scheduler` / `agent.plugin_ctx.gateway_registry`。
- **session_id**：**去作用域**。`agent.run(prompt)` 无 session_id；Wave 3 单 session（见 §6）。`submit(prompt)`、`handle_inbound(source, chat_id, message)` 均路由到 `agent.run(message)`。
- **WebhookGateway 启停**：`uvicorn.Config(app, host=..., port=0, log_level=...)` + `Server(config)`；`start()` 用 `asyncio.create_task(server.serve())`，`stop()` 设 `server.should_exit = True`。`port=0` -> OS 分配，启动后读 `actual_port`（从 server sockets）。
- **cron 解析器**：修异常吞 + weekday 约定（Sun=0）+ 诚实 docstring；完整 cron/库 = OUT。
- **ctx.runtime**：不加。job handler 走 `ctx.agent.run(...)`（`agent` 已在 PluginContext）。
- **CLI 单 loop 合并**：`Agent.create` 移入 `runtime.start()`；`_setup_agent` 返回未启动 Runtime（+ config_source），`repl()` 协程内 `await runtime.start()` -> dashboard 构造 -> REPL -> `finally: await runtime.stop()`。
- **GatewayRegistry 容器归属**：Agent 构造并挂 ctx（仿 `loop_policies`）；与 scheduler（SchedulerPlugin 构造）模式相反但两者已在 codebase 共存。
- **§4.4 事实校正**：`fastapi` 已被 `web/app.py` 使用（非"声明未用"）；仅 `uvicorn` 此前未用。

## 13. 验收标准

1. `AgentRuntime.start()` 后 CronScheduler 真启动、GatewayRegistry `start_all` 完成；`stop()` 幂等清干净。
2. `WebhookGateway` 端到端：POST 消息 -> 经 Runtime 路由 -> agent 回复 -> HTTP 响应（集成测试通过）。
3. 插件可通过 `ctx.register_gateway(adapter)` 动态注册网关，运行时被 `start_all` 拉起。
4. 去债 gates：`DeliveryManager`/`TaskManager`/`BaseGateway`/`telegram.py`/`discord.py` 零残留；`pass` stub 零残留；cron 异常不吞。
5. CLI 单事件循环：`run_repl` 内 start/stop Runtime，REPL 行为零回归（CLI 测试套件绿）。
6. 全量测试套件绿（在 Wave 2 的 949/1/0 基础上新增 Wave 3 测试）。
