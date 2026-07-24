---
name: project-vision
description: "Mercury Code (merco) project vision, architecture, design decisions, development guidelines, coding standards, milestones, tech stack, and project conventions. Use when working on merco: planning features, making architecture decisions, understanding project direction, or implementing code."
---

# Mercury Code (merco) 项目愿景

混合型 AI Agent 框架，融合两家主流 Agent 框架的核心优势，构建一个**轻量、高效、可落地**的 Python 智能开发助手。

## 核心目标

1. **杂交优势** — 继承成熟的 Agent 循环机制、Skill 系统、MCP 协议、多代理协作
2. **精简架构** — 移除冗余抽象层，聚焦核心开发场景
3. **Python 原生** — uv/pyproject.toml，asyncio 异步生态
4. **落地优先** — 每个功能有明确使用场景，避免过度工程化

## 开发环境

```bash
# 首次安装依赖
cd /home/xiowen/code/merco
uv sync

# 全局安装（之后任意目录直接敲 merco）
uv tool install -e .
# 注意：-e 是 editable 安装，改代码后无需重新 install，只有加新依赖才需要 --reinstall

# 运行
merco                  # 直接启动交互模式（无需子命令）
merco --debug          # 调试模式
merco -m MiniMax-M2.5  # 指定模型
merco run              # 显式 run 子命令，同上
merco init             # 初始化项目配置
merco skills -l        # 列出技能
```

> 实现方式：`@app.callback(invoke_without_command=True)` 注册为 Typer 回调，通过 `ctx.invoked_subcommand is None` 判断无子命令时进入交互模式。`run` 子命令通过共享 `_setup_agent()` + `run_repl()` 函数消除代码重复。

## 当前状态

**Wave 1+2+3 插件/模型/gateway 动态化完成 + 技术债清零** | 插件系统：Plugin ABC + PluginContext（23 扩展点 + 11 便捷方法）+ PluginDiscovery（entry_points + 目录扫描）+ PluginManager（Kahn 拓扑 + priority）；**8 个内置插件**（observability/skills/mcp/subagent/web/gateway/scheduler/superpower）经 `merco.plugins` entry-points 动态发现 | 模型层：`ModelProvider` ABC + `ModelRegistry` 单一真相源（OpenAICompatible + AnthropicNative 双 provider，`select()` 独占凭证解析）| Gateway 层：`GatewayAdapter` ABC + `GatewayRegistry` + `WebhookGateway` 参考适配器 + `AgentRuntime` 薄宿主统一生命周期 | 代码质量：**ruff check 0 / ruff format 干净 / pre-commit 强制 / 999 tests passed / 0 skipped / 0 failures** | 对标 Hermes/OpenClaw/OpenCode | 最后更新: 2026-07-24

### Wave 1+2+3 + 去债浪潮（2026-07-23 ~ 2026-07-24）

| 工作 | 周期 | 关键产出 | 终态 commit |
|------|------|----------|-------------|
| Wave 1 插件动态化 | 2026-07-23 | `PluginDiscovery` + `PluginSpec` + `PluginManager` (Kahn 拓扑 + priority) + 两阶段 boot | `d99cc87` |
| Wave 2 模型层动态化 | 2026-07-23 | `ModelProvider` ABC + `ModelRegistry` 单一真相源 + OpenAICompatible / AnthropicNative 双 provider | `4951099` |
| Wave 3 多入口动态化 | 2026-07-24 | `GatewayAdapter` ABC + `GatewayRegistry` + `WebhookGateway` + `AgentRuntime` 薄宿主 + CLI 单事件循环 | `d92d958` |
| 去债浪潮（T1-T8） | 2026-07-24 | ruff 498→0（零规则禁用纯修根因）；`.pre-commit-config.yaml` 本地 `uv run ruff` 钩子 | `d92d958` |
| 测试跳过修复 | 2026-07-24 | dash `printf` 不支持 `\x` 十六进制转义（真 bug），cat 二进制文件替 printf | `e7dd024` |

**下一焦点候选**详见 [next-focus.md](references/next-focus.md)（推荐 Gateway 生态扩展，Self-Improving Loop 延后）。

## 详细文档

| 文档 | 内容 |
|------|------|
| [项目进展](references/progress.md) | 已完成清单（Wave 1+2+3 + 去债 + 测试跳过修复）、骨架待实现、里程碑、下一步候选 |
| [架构设计](references/architecture.md) | 模块设计、目录结构、技术栈、参考资料库、收尾模式、AgentRuntime 宿主 |
| [关键决策](references/decisions.md) | 重要决策记录与原因（按日期倒序） |
| [开发教训](references/lessons.md) | 犯过的错、反思、以后的规则 |
| [下一焦点](references/next-focus.md) | 候选方向对比（Gateway 扩展推荐 / per-chat_id 路由 / Self-Improving Loop 延后） |
| [Bug 追踪](references/bugs.md) | 已修复和待修复的 bug |

## 工作原则

**重大改动前**：先说明计划 → 等待确认 → 分步执行

1. **简单优于复杂** — 能写函数就不写类
2. **约定优于配置** — 提供合理默认值
3. **渐进式实现** — 先跑起来，再优化，最后重构
4. **测试驱动** — 核心逻辑必须有单元测试覆盖
5. **根因优先** — 修改 bug 必须先找到根因，再根据根因修复。禁止只修表面症状（如加 `except: pass`、在调用方 try/catch 掩盖源头问题）。修复前必须评估对总体架构的影响和副作用。
6. **同类全检** — 修一个方法/文件时，必须搜索并同步修复所有同类代码。
7. **核心无关 provider** — `core/` 层代码的注释、变量名、逻辑中禁止出现任何具体 provider 名。
8. **通解不补丁，可拓展不硬编码** — 纠正 bug 时必须问：这是当前场景的补丁还是所有同类问题的通解？通解必须可被其他功能复用、可拓展到新场景。每个"智能"功能必须配一个"我不认识这个"的 fallback。
9. **注释写为什么，不写怎么做** — 代码注释描述设计意图和边界条件，不描述变更历史和操作步骤。

## Bug 修复流程

1. **写根因陈述** — 一句话描述为什么会出现这个 bug
2. **检查架构影响** — 这个 bug 属于哪个模块？修复会不会影响后续 Phase 规划？
3. **最小修复** — 只改根因涉及的代码行，不顺手改别的
4. **副作用检查** — 会不会让其他地方炸？要不要加 guard/fallback？
5. **验证** — 复现 → 确认修好，不能只靠推测
6. **记录** — 修复后必须立即更新 `bugs.md`（含根因 + 修复方案）

## 同步机制

修改 `docs/project-vision/` 下任何文件后，需同步到 agent 的 skill 目录:

```bash
# 同步到 .merco/skills/
cp docs/project-vision/SKILL.md ~/.merco/skills/project-vision/
cp docs/project-vision/references/*.md ~/.merco/skills/project-vision/references/
```

**更新纪律**：每次重大提交后，必须根据提交内容更新 `progress.md`（模块状态变更）、`decisions.md`（新决策）、`architecture.md`（架构变更），然后同步到所有位置。不要在代码变更后留下过期的 skill 文档。

## 注意事项

- 保持 MVP 思维，不过度设计
- 每个新功能要回答：用户为什么需要它？
- 优先复用成熟库，遵循 PEP 8
