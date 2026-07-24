# Next Focus — 投入方向

> 最后更新: 2026-07-24
> 状态: 候选方向对比中（Wave 1+2+3 + 去债 已完成，**下一焦点待定**）

## 上下文

2026-07-23 ~ 2026-07-24 期间，merco 完成了**三大动态化浪潮 + 一轮系统去债**：

| 浪潮 / 工作 | 周期 | 关键产出 | 终态 |
|------------|------|----------|------|
| **插件动态化 波1** | 2026-07-23 | `PluginDiscovery` (entry_points + 目录扫描) + `PluginSpec` + `PluginManager` (Kahn 拓扑 + priority) + 两阶段 boot；7 个 builtin 经 entry_points | commit `d99cc87` |
| **插件动态化 波2** | 2026-07-23 | `ModelProvider` ABC + `ModelRegistry` 单一真相源 + `OpenAICompatibleProvider` / `AnthropicNativeProvider`；凭证解析归 `select()` 独占 | commit `4951099` |
| **插件动态化 波3** | 2026-07-24 | `GatewayAdapter` ABC + `GatewayRegistry` + `WebhookGateway` 参考适配器 + `AgentRuntime` 薄宿主；CLI 单事件循环重构；删 5 死文件 | commit `d92d958` |
| **去债浪潮** | 2026-07-24 | ruff 498→0（零规则禁用，纯修根因）；`.pre-commit-config.yaml` 本地 `uv run ruff` 钩子；T1-T8 八任务全绿 | commit `d92d958` |
| **测试跳过修复** | 2026-07-24 | dash `printf` 不支持 `\x` 十六进制转义——真 bug，cat 二进制文件替 printf | commit `e7dd024` |

**终态指标**：
- 999 passed / 0 skipped / 0 failed（去债 8 任务 + dash bug 修复后全绿）
- `ruff check .` 0 error
- `ruff format --check .` 0 diff
- pre-commit 强制门（`.pre-commit-config.yaml`，本地 `uv run ruff`，防版本漂移）
- 8 个内置插件（observability/skills/mcp/subagent/web/gateway/scheduler/superpower），priority 数据驱动 boot 序
- `PluginContext` 23 注入属性 + 11 便捷方法
- `merco/core/runtime.py` (`AgentRuntime`，~116 行) 薄宿主统一 Agent + CronScheduler + GatewayRegistry 生命周期

旧的 `next-focus.md`（2026-06-16）锁定 **Self-Improving Agent Loop** 为下一站，但**该决策在 Wave 1/2/3 + 去债 之前**做出——基础设施语义已变，且 Self-Improving Loop 的数据出口（`tool.error` / `conversation.turn` / `llm.chat` hooks、Memory 双向打通、`HybridRecaller`）现已全部验证为可用。**候选需要重新评估**。

---

## 已完成的浪潮（2026-07-23 ~ 2026-07-24）

### Wave 1 插件动态化（commit `d99cc87`）
- `PluginDiscovery`（~190 行）吃 `config` 产出 `PluginSpec`，无副作用；两源发现：entry_points + 目录扫描（`plugin.toml` manifest，`importlib.util.spec_from_file_location` 单文件加载，零 `sys.path` 污染）。
- `PluginManager.register_all(specs)` + `_resolve_order()` Kahn 拓扑 + `(-priority, name)` tiebreak；两阶段 boot（`activate_boot()` priority≥100 → bind observer → restore context → `activate_all()`）。
- `agent.py` ~70 行硬编码 import 折成单行 `PluginDiscovery(config).discover()` + `register_all`；零 `from merco.plugins.builtin.*` 残留。
- `PluginContext` 注入属性 20→**20（含 security_pipeline）** + 便捷方法 **4**（`register_agent_profile` / `register_loop_policy` / `add_memory_backend` / `add_security_policy`）。
- 7 个 builtin 经 entry_points：observability(100) / skills(60) / mcp(50) / subagent(40) / web(30) / scheduler(20) / superpower(10)。

### Wave 2 模型层动态化（commit `4951099`）
- `merco/core/llm/` 拆分：`base.py`（`ModelProvider` ABC + `ModelProviderInfo`）+ `registry.py`（`ModelRegistry` 单一真相源）+ `openai_provider.py`（吸收旧 `LLMClient`）+ `anthropic_provider.py`（原生 Messages API，证明 ABC 不被 OpenAI 形状绑架）+ `thinking.py` / `response.py` / `errors.py` / `error_ui.py`。
- `ModelRegistry.select()` **独占凭证解析**（`key_env` → env → config → `ModelConfig.api_key`），agent/config 不再各自补 base_url/api_key。
- 删旧 `_client.py` / `PROVIDER_REGISTRY` / `ProviderInfo` / `LLMClient` / `MockLLMClient` / `ProgrammableLLMClient` 及全部迁移别名（**no-debt gate**）。
- `PluginContext.model_registry` + `register_model_provider()` 新增（5 个便捷方法）；`MemoryStrategy` 改用 deferred provider getter。

### Wave 3 多入口动态化（commit `d92d958`）
- `merco/gateway/{base,registry,webhook}.py`（共 ~270 行）：`GatewayAdapter` ABC（`set_message_handler` 推模式契约） + `GatewayRegistry`（per-adapter 失败隔离，`_bound(_name=name)` 默认参防晚绑定） + `WebhookGateway`（FastAPI/uvicorn，`port=0` OS 分配，`actual_port` 从 `server.servers[0].sockets[0].getsockname()[1]` 提取）。
- `merco/core/runtime.py`（`AgentRuntime`，~116 行）薄宿主：owns Agent + CronScheduler + GatewayRegistry；`start()/stop()` 幂等；`submit(prompt)` 给 cron；`handle_inbound(source, chat_id, message)` 给 gateway inbound。
- **Wave 3 单 session 简化**：`handle_inbound` 当前 `agent.run(message)`，`chat_id` 保留前向兼容**但不启用 per-chat_id 隔离**（spec §6 descope）。
- `GatewayPlugin` 第 8 内置插件 priority=**25**；`PluginContext.gateway_registry` + `register_gateway()` 新增（11 个便捷方法）。
- CLI 单事件循环重构：`_setup_agent()` 改 sync 返回**未启动** Runtime；`repl()` 内 `await runtime.start()` / `finally: await runtime.stop()`；全文件仅一处 `asyncio.run(repl())`（cli/main.py:571）。
- 删 5 死文件：`cli/tui.py` / `merco/tools/mcp_tools.py` / `merco/gateway/{telegram,discord}.py` / `merco/scheduler/{delivery,jobs}.py`。

### 去债浪潮（commit `d92d958`，T1-T8）
- T1 死代码 stub 删除（`ab20c07`）：`cli/tui.py`（Phase 7 TUI 占位）+ `merco/tools/mcp_tools.py`（MCP 真身在 `merco/mcp/`，此为 stub）。
- T2 真实类型洞修复（`dafa879`）：4 F821 + 1 F811 + 3 F841。
- T3 F401 未用 import 大扫除（`3b495d9`）：86→0，**先标注 side-effect import 再 autofix**（`cli.commands` 触发 `@cmd_registry.register` 装饰器 → noqa；sandbox `_DEFAULT_RULES` 加进 `__all__`）。意外发现并修复 52 集成测试断（`_isolation_services` fixture 被误删）。
- T4 ruff autofix 简单项（`4b4facd`）：I001 203→0 + W292 16→0 + F541 12→0。
- T5 pyupgrade（`83f9b7c`）：UP037 59→0 + UP035 11→0；判定安全（仓库零运行时注解求值 + 全 `from __future__ import annotations`）。
- T6 ruff format 全仓（`50c511a` 上半）：191 文件纯格式化。
- T7 手动残余清理（`2dfa556`）：N818 / N806 / F841 / E501 / F811 / E731 / UP042。
- T8 pre-commit 钩子（`d92d958`）：`.pre-commit-config.yaml` 本地 `uv run ruff`（与项目 venv 版本对齐）。**pyproject.toml `[tool.ruff]` 零改动**——零规则禁用，纯靠修复达成 0 error。

### 测试跳过修复（commit `e7dd024`）
- 根因：dash `printf` 不支持 `\x` 十六进制转义——`printf '\xff\xfe\xfd'` 输出字面字符串（含反斜杠与字母），断言 `assert "�" in stdout` 不可能通过。
- 修复：cat 一个真实二进制文件（`b"\xff\xfe\xfd"` 由 Python `tmp_path` 写入）。
- 结论：跳过不是 stale debt，是真 bug；shell 兼容性靠 `pytest.skip` 掩盖了 6 个月。

---

## 决策：下一焦点 = **Gateway 生态扩展**（推荐）

> 决策置信度：中。下列候选对比表 + reasoning。**最终决定需用户确认**——此 doc 的目的是把比较框架立起来，不是替用户拍板。

**候选按推荐度排序**：

### 候选 A：Gateway 生态扩展（⭐ 推荐）

**一句话**：在 `WebhookGateway` 之外新增 1-2 个参考适配器（`TelegramGateway` / `DiscordGateway`），从"有架构"走到"真用上"。

**为什么 now**：
- **架构已就位**（Wave 3 0→1 成本已付），扩展边际成本 = 写一个 `GatewayAdapter` 子类 + `activate(ctx)` 注册。
- **删除的 stub 暗示产品意图**：`merco/gateway/{telegram,discord}.py` 曾在 Wave 3 准备期被 `97e70fc` 删——这两个适配器位置是 merco 早期规划过的入口，删只是因为它们当时是死代码。
- **价值验证路径短**：跑通 Telegram/Discord → 真实用户在真实 IM 里使用 → 反过来证明 `AgentRuntime` + `GatewayRegistry` 的设计选择（薄宿主 + 失败隔离 + 推模式 handler）合理。
- **差异化**：hermes/openclaw 也有多平台 gateway，但 merco 的"插件动态化"架构 + 失败隔离 + 模型层可替换（Anthropic 原生）让接入新平台 = 写 ~80 行 adapter + `register_gateway()`，**不需改 agent.py**。

**为什么不 later**：
- 越 later，`AgentRuntime` 抽象越僵化（被生产用例反推修改）；现在补 1-2 个真实适配器，边界设计才能定型。
- 推迟到 Phase 7（多代理协作）就晚了——届时 gateway 是 multi-agent 调度的一部分，但基础适配器契约不成熟会让 Phase 7 重构。

**预计工作量 / 风险**：
- 工作量：1-2 个适配器 × ~80 行 = **~150-200 行新增 + 集成测试**；Telegram Bot API 简单（httpx + 长轮询或 webhook 双向），Discord 类似。
- 风险：低。`WebhookGateway` 已验证 FastAPI/uvicorn 模式可跑（port=0 集成测试有），长连接类（Telegram long poll）需要新模式但仍然隔离在 adapter 内部。
- 凭证：Telegram/Discord bot token 走 env 变量（与现有 `ModelConfig.key_env` 一致）。

**不破坏现有**：
- 增量：每个适配器独立文件 + 独立 entry_point（不强制打包到 `GatewayPlugin`），或者塞进 `GatewayPlugin` 内 `register_gateway()` 多调用。
- `AgentRuntime.handle_inbound` 已经预留 `source` 参数（"telegram" / "discord" / "webhook"），无需新签名。

### 候选 B：Multi-Session / per-chat_id 路由

**一句话**：把 Wave 3 descope 的 `handle_inbound(source, chat_id, message)` 真正实现——不同 `chat_id` 路由到不同 SessionStore entry，互不串上下文。

**为什么 now**：
- **Wave 3 留的口子**：`chat_id` 已在 `handle_inbound` 签名里，前向兼容已就位；不做就是 spec §6 的技术债。
- **真实场景需求**：Telegram 群里多个用户同时跟 agent 对话；当前所有 inbound 共享同一个 session，互相串。

**为什么不 first**：
- **依赖候选 A**：真要做 per-chat_id 路由，至少要先有 1 个非 webhook 的 gateway 适配器（Telegram/Discord）才能验证——纯 webhook 没人用多 chat_id。
- **SessionStore 改造**：`SessionStore` 当前是单数据库 + 启动时 `resume_or_create()` 单 session；要做 per-chat_id 需要 SessionStore 加 `find_by_chat_id(source, chat_id)` + Agent 启动时按 `chat_id` 选 session（而非单 `resume_or_create`）。改动波及 Agent 装配段（已 1186 行）。
- **并发问题**：per-chat_id session 让 Agent 单例 vs 多实例成问题——`AgentRuntime` 持有单 Agent，但多 chat_id 是要 1 个 agent 处理 N 个 session，还是 N 个 agent × N 个 session？spec 要先定。

**预计工作量 / 风险**：
- 工作量：spec (~50 行) + SessionStore 改造 (~100 行) + Agent 装配改造 (~50 行) + AgentRuntime 选择策略 (~50 行) + 测试 (~200 行) = **~450 行 + 集成测试**。
- 风险：中。并发模型（单 agent + 多 session queue / 多 agent）需要 spec 决策，**不能直接开做**。

### 候选 C：Self-Improving Agent Loop（原始候选，已延后）

**一句话**：订阅 `tool.error` / `conversation.turn` / `llm.chat` → `FeedbackDetector` 识别触发条件 → `Improver` 调 LLM 看具体失败 case 生成"应该怎么做"的 prompt-level 教训 → 写 Memory（`source=system` priority=1）→ 下次 `agent.run` 经 `HybridRecaller` 召回注入 system prompt。

**为什么 now**（原 next-focus.md 论证）：
- 架构复用率最高（Observer / Memory / Hook / Pipeline 零新基础设施）
- merco 独家路径（hermes 是 fine-tuning，merco 做 prompt-level 轻量即时）
- 不破坏现有架构（增量加 `SelfImprover`）
- 可见价值（用户用越久 agent 越懂自己）

**为什么 not now**（重评估后）：
- **观测数据还没积累**：`Observer` 双计数器 + 999 测试全 mock LLM——真用户跑起来后才有"tool.error 频率 / 单次 token / 用户纠正"等真实数据。在 mock-only 阶段设计 FeedbackDetector 是设计空气。
- **优先级反转**：自进化是 **"用得多"才有用** 的能力；先有真实用户（候选 A 推动）+ 真实 chat 路由（候选 B）才有"用得多"。**应该排在 A 和 B 之后**，不是之前。
- **质量难验证**：LLM 生成的"教训"好坏需要**人工评审数据集**（merco 没有），当前阶段上 Self-Improving 容易产出"教训垃圾"污染 memory。
- **YAGNI 边界扩大**：原 plan 已声明不做 fine-tuning / 跨 agent 共享 / 经验图谱 / RLHF / 经验 TTL / 自动重写历史——但**经验冲突 + 经验过期 + 经验质量低**这些 Phase 4 边界 case 极难做对，会把团队精力拖进 6 周迭代。

**预计工作量 / 风险**：
- 工作量：phase 1-3 ≈ **~800 行 + 100+ 测试**；phase 4 边界 case ≈ **~300 行 + 50+ 测试**。
- 风险：中-高。失败时主循环被污染（"教训"塞进 memory，下次召回注入 system prompt）。fail-soft 兜底可以缓解，但**首次 pollute 后排查极难**（memory 是黑盒）。

**保留为延后候选**：等候选 A+B 落地后（6-8 周后），merco 会有真实用户 + 真实 chat 路由，彼时 Self-Improving 的输入数据才真实。

### 候选 D：Web 对接 Agent（Phase 7 计划）

**一句话**：`web/app.py` 当前 `/chat` 返回 `"coming soon"`——接上 `AgentRuntime.submit(prompt)` 让 HTTP 也能跑 agent。

**为什么 now**：
- **架构已就位**：`AgentRuntime.submit()` 已是 web 唯一需要的方法（cron job 也在用），几乎零 Agent 改造。
- **GatewayPlugin 不必独占入站**：web HTTP 也是一种"gateway"，可经 `WebhookGateway.outbound_url` 实现，不一定新建 `WebGateway`。
- **落地快**：~50-100 行（FastAPI 端点 + `runtime.submit` 调用 + 流式输出） + 测试。

**为什么不 first**：
- **与候选 A 高度重叠**：web 入口 vs Telegram/Discord 入口本质都是"外部 HTTP-like → agent"，做 web 之后再做 Telegram adapter 时会发现 `WebhookGateway` 改造在两边都被反推，不如先做真实 IM 适配器定型契约。
- **Web 用户验证价值不如 IM**：web 是开发者工具型 UI，Telegram/Discord 是真实用户场景，**后者更能验证 `AgentRuntime` 的可移植性**。

**预计工作量 / 风险**：
- 工作量：**~150-200 行 + 集成测试**。
- 风险：低。复用 Wave 3 Runtime 抽象。

**保留为后续候选**：候选 A 落地后再做 web 对接，共享同一套 Runtime 抽象。

---

## 决策依据（候选对比表）

| 维度 | 候选 A: Gateway 扩展 | 候选 B: per-chat_id 路由 | 候选 C: Self-Improving Loop | 候选 D: Web 对接 Agent |
|------|---------------------|--------------------------|------------------------------|------------------------|
| **依赖已有架构** | 完全复用 Wave 3 抽象 | 依赖 A（真要 IM 才有意义） | 完全复用 Observer/Memory/Hook | 完全复用 AgentRuntime.submit |
| **新代码量** | ~150-200 行 | ~450 行 | ~800-1100 行 | ~150-200 行 |
| **测试量** | ~200-300 行 | ~300-500 行 | ~150-300 行 | ~100-200 行 |
| **风险** | 低 | 中（并发模型需 spec） | 中-高（污染 memory 难排查） | 低 |
| **用户可见价值** | 高（真实 IM 用上） | 高（多用户隔离） | 中-高（需先有真实数据） | 中（开发者工具） |
| **差异化** | 高（hermes/openclaw 也做但路径不同） | 中 | 高（prompt-level 自进化独家） | 低（每家都有） |
| **spec 决策** | 无（沿用 Wave 3 契约） | 需 spec（并发模型） | 需 spec（边界 case 多） | 无（FastAPI + submit 即可） |
| **是否需外部凭证** | 是（Telegram/Discord token） | 否 | 否 | 否 |
| **是否依赖真用户数据** | 否 | 否 | 是 | 否 |
| **预计总周期** | 1-2 周 | 2-3 周 | 4-6 周 | 1 周 |
| **与 Phase 7 关系** | 直接铺垫 | 直接铺垫 | 间接（可独立） | 直接铺垫 |

**综合评分**：
- 候选 A：价值/工作量比最高，**风险最低**，架构已就位 → **推荐第一波**。
- 候选 B：价值高但有 spec 决策成本，**排在 A 之后**。
- 候选 C：原 next-focus 锁定，重评估后**延后**（等真用户数据）。
- 候选 D：低风险低差异化，**排在 A 之后**做 web 不浪费 Runtime 抽象。

**推荐路径**：
1. 候选 A：1-2 个 IM 适配器（Telegram 优先，Discord 可选），定型 `GatewayAdapter` 契约
2. 候选 D：web `/chat` 对接 `runtime.submit`，复用 Runtime
3. 候选 B：per-chat_id 路由（基于 A/D 的真使用经验）
4. 候选 C：Self-Improving Loop（基于 A/B/D 累积的真实数据 + 真实 chat 场景）

---

## 已废弃的候选（原始 next-focus.md 提到的）

| 候选 | 决策 | 原因 |
|------|------|------|
| Multi-Modal Context 引擎 | 暂缓 | scope 大、依赖重，三家对标都没把它当核心 |
| Agent Composition（子 agent 编排） | 暂缓 | 工程量大、各家都在做、无差异化（与候选 C 类似的"先等真用户"理由） |

---

## 候选 A 详细执行计划（推荐首波）

> **前提**：用户/团队确认 Gateway 扩展为下一焦点。

### Phase 1: TelegramGateway 参考实现（基础）
- `merco/gateway/telegram.py` (~80 行)：httpx 调 `getUpdates` 长轮询 OR `setWebhook` 双向；`chat_id` 来自 `update.message.chat.id`；`send_message` 调 `sendMessage` API。
- 在 `merco/plugins/builtin/gateway/plugin.py` 的 `activate()` 内 `ctx.register_gateway(TelegramGateway())`（与 `WebhookGateway` 并列）。
- 凭证：env `TELEGRAM_BOT_TOKEN`（与 `ModelConfig.key_env` 风格一致）。

### Phase 2: 集成测试
- `tests/gateway/test_telegram.py`：mock httpx，模拟 `getUpdates` 返回 + `sendMessage` 调用，验证 `handle_inbound` 路由到 `agent.run`，reply 通过 `send_message` 回去。
- 复用 `tests/gateway/test_webhook.py` 的 capture_console + make_fake_agent 模式。

### Phase 3: 凭证解析 + 文档
- `merco/core/config.py` 新增 `telegram_bot_token` 字段（与现有 `mcp_servers` 配置风格一致）。
- `README.md` 加 Telegram 启动示例 + `merco.json` 字段。

### Phase 4（可选）: DiscordGateway
- 类似 Telegram，但 Discord API 略复杂（gateway websocket 或 webhook 双向）。

### YAGNI 边界（不做）
- 不做 IM 富文本渲染（先 raw text）
- 不做消息去重（`update_id` 简单 skip）
- 不做群聊 vs 私聊分支（统一 `chat_id`）
- 不做多 bot 并存（单 bot 单 token）

---

## 下一步

- **若同意候选 A**：进入 brainstorming skill，产出 spec → plan → 执行
- **若选其他候选**：更新本文档"决策"段，更新 progress.md 里程碑
- **若多选并行**：建议 A 先（1-2 周），再 A+D 并行（再 1 周），再 B（再 2-3 周）
