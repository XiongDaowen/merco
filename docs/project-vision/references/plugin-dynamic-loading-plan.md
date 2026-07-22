# 插件动态化三波路线

> 最后更新: 2026-07-23
> 状态: 已定方向，逐波推进

## 背景

当前插件系统底座已有（`Plugin` ABC + `PluginContext` 19 扩展点 + `PluginManager` 生命周期 + 8 个 builtin 插件），但插件是**编译期硬编码**的，不是运行期动态安装的：

- 8 个 builtin 插件在 [agent.py:448-514](../../../merco/core/agent.py#L448-L514) 硬编码 import + register
- 激活顺序在 [agent.py:534-545](../../../merco/core/agent.py#L534-L545) 硬编码
- `PluginManager.register()` 吃的是已 import 的实例，无发现机制
- 无 manifest 元数据 / 无依赖与优先级解析

**目标**：让外部插件可动态安装进来，不动 agent.py，架构清爽。

## 核实纠正（动手前必读）

代码核实发现文档与现实已脱节，动手前必须以代码为准：

- **P2 PermissionPolicy 已实现**（roadmap 文档滞后）：[guard.py:145-195](../../../merco/sandbox/guard.py#L145-L195) 已有 `PermissionPolicy` ABC + `PolicyPipeline` + `BuiltinDefaultPolicy`；[agent.py:350-355](../../../merco/core/agent.py#L350-L355) 已装配 `self._security_pipeline`。只是 `PluginContext` 未暴露 `security_pipeline`。
- **ModelProvider / GatewayRegistry 确实不存在**，需新建。
- **Scheduler 仍 NOT WIRED**（见 [progress.md](progress.md)）：`SchedulerPlugin` 已注册但 `CronScheduler` 未在 CLI/Runtime 真正启动。
- **便捷方法现状**：`PluginContext` 有 `register_tool` / `add_prompt_chunk` / `add_processor` / `add_recaller`，缺 `register_agent_profile` / `register_loop_policy` / `add_memory_backend` / `add_security_policy`。

## 三波路线

### 波1：地基（动态加载 + 扩展点一致化）

**动态加载层**：

- `PluginManager` 增加 `discover()`（或独立 `PluginDiscovery`）
- 支持 entry_points（`merco.plugins` group）自动发现
- 支持本地插件目录扫描（`~/.merco/plugins/`）
- `PluginSpec` manifest 元数据格式（name / version / priority / depends_on / entry）
- 激活顺序由硬编码改为 priority + depends_on 拓扑排序
- 把 [agent.py:448-514](../../../merco/core/agent.py#L448-L514) 硬编码的 7 个 builtin register 改为走 discovery（builtin 作为内置 spec）

**扩展点一致化（便捷方法）**：

- `ctx.register_agent_profile(profile)`
- `ctx.register_loop_policy(policy)`
- `ctx.add_memory_backend(backend)`
- `ctx.add_security_policy(policy)` —— 先把 `agent._security_pipeline` 暴露到 `PluginContext`

**验证标准**：外部插件（目录或 entry_point）能被发现、按序激活、注册工具/profile/policy；`agent.py` 不再硬编码插件列表；现有 8 个 builtin 插件行为不变。

### 波2：模型层（ModelProviderRegistry）

- `ModelProvider` ABC（`chat` / `chat_stream`）
- `ModelRegistry` + 多模型路由（cost / quality / speed 策略）
- 替换 `LLMClient` 硬编码 provider dispatch
- 动 [core/llm.py](../../../merco/core/llm.py)，独立验证

### 波3：多入口（Scheduler 接 Runtime + GatewayRegistry）

- 先补 P4：`CronScheduler` 接入 CLI/Runtime（progress.md 标 NOT WIRED）
- 再做 P5：`GatewayAdapter` ABC + `GatewayRegistry` + 消息路由
- Gateway 依赖一个活着的 Runtime 入口，故 Scheduler 接入在前

## 范围边界

三波完成 = **插件层完整**，非"项目完美"。以下不在本路线内（见 [progress.md](progress.md) 的 NOT WIRED）：

- TUI（`tui.py` 仍占位）
- Web -> Agent（`/chat` 返回 "coming soon"）
- SubAgent 多代理协作

## 原则

- 每波独立可验证、可回滚
- 每波遵守 project-vision 工作原则（根因优先 / 通解不补丁 / 测试驱动）
- 动手前先核对 roadmap vs 代码差异，避免重复造轮子（P2 即为先例）
