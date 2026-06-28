# Phase 3.6：SchedulerPlugin 设计规格

> 日期: 2026-06-28
> 基于: `docs/project-vision/references/architecture-refactor-plan.md`
> 前置: Phase 3.1-3.5 已完成

## 背景

`CronScheduler` 在 `merco/scheduler/cron.py` 中已定义，但没有任何生产代码引用它。它是一个纯骨架——cron 表达式调度器，支持 `add_job`/`remove_job`/`start`/`stop`。

架构审查报告列为 3.6：`scheduler → SchedulerPlugin`。

## 目标

1. 新增 `SchedulerPlugin`，创建 `CronScheduler` 并写入 `ctx.scheduler`。
2. `PluginContext` 增加 `scheduler` 字段。
3. `Agent.create(...)` 激活 `scheduler` 插件。
4. 不自动启动调度器——调用方显式触发 `scheduler.start()`。

## 非目标

- 不自动注册 cron jobs。
- 不把 scheduler 接入 CLI / Agent.run()。
- 不实现完整的 cron 解析。
- 不修改 CronScheduler 本身。

---

## 设计

### 1. SchedulerPlugin

新增 `merco/plugins/builtin/scheduler/plugin.py`：

```python
class SchedulerPlugin(Plugin):
    name = "scheduler"
    version = "1.0.0"
    description = "Creates the cron scheduler"

    async def activate(self, ctx):
        from merco.scheduler.cron import CronScheduler
        ctx.scheduler = CronScheduler()
```

### 2. PluginContext 扩展

```python
scheduler: CronScheduler | None = None
```

### 3. Agent 初始化

- 注册 `SchedulerPlugin`（在 WebPlugin 之后、SuperpowerPlugin 之前）
- `_initialize_async_plugins()` 激活 `scheduler` 在 `web` 之后、`activate_all()` 之前

### 4. 激活顺序

```text
observability → restore → skills → mcp → subagent → web → scheduler → activate_all
```