---
name: project-vision
description: "OpenMercury project vision, architecture, design decisions, development guidelines, coding standards, milestones, tech stack, and project conventions. 项目愿景、架构设计、开发指南、编码规范、技术决策、里程碑、技术栈。Use when working on OpenMercury: planning features, making architecture decisions, understanding project direction, or implementing code."
---

# OpenMercury 项目愿景

混合型 AI Agent 框架，融合两家主流 Agent 框架的核心优势，构建一个**轻量、高效、可落地**的 Python 智能开发助手。

## 核心目标

1. **杂交优势** — 继承成熟的 Agent 循环机制、Skill 系统、MCP 协议、多代理协作
2. **精简架构** — 移除冗余抽象层，聚焦核心开发场景
3. **Python 原生** — uv/pyproject.toml，asyncio 异步生态
4. **落地优先** — 每个功能有明确使用场景，避免过度工程化

## 开发环境

```bash
# 首次安装依赖
cd /home/xiowen/code/OpenMercury
uv sync

# 全局安装（之后任意目录直接敲 openmercury）
uv tool install -e .
# 注意：-e 是 editable 安装，改代码后无需重新 install，只有加新依赖才需要 --reinstall

# 运行
openmercury                  # 直接启动交互模式（无需子命令）
openmercury --debug          # 调试模式
openmercury -m MiniMax-M2.5  # 指定模型
openmercury run              # 显式 run 子命令，同上
openmercury init             # 初始化项目配置
openmercury skills -l        # 列出技能
```

> 实现方式：`@app.callback(invoke_without_command=True)` 注册为 Typer 回调，通过 `ctx.invoked_subcommand is None` 判断无子命令时进入交互模式。`run` 子命令通过共享 `_setup_agent()` + `run_repl()` 函数消除代码重复。

## 当前状态

**Phase 1 完成 → Phase 2 起步** | 20 REAL + 7 PARTIAL + 12 SKELETON + 6 NOT WIRED | 收尾方案定型：_wrap_up_messages + _wrap_up_call | 幻觉校验始终执行 + 四层防线 | 压缩重写（token 滑动窗口 + 链完整 + LLM 语义摘要） | 对标 Hermes/OpenClaw/OpenCode | 最后更新: 2026-05-23

## 详细文档

| 文档 | 内容 |
|------|------|
| [项目进展](references/progress.md) | 已完成清单、骨架待实现、里程碑、下一步计划 |
| [架构设计](references/architecture.md) | 模块设计、目录结构、技术栈、参考资料库、收尾模式 |
| [关键决策](references/decisions.md) | 重要决策记录与原因 |
| [开发教训](references/lessons.md) | 犯过的错、反思、以后的规则 |
| [Bug 追踪](references/bugs.md) | 已修复和待修复的 bug |
| [Phase 1 Bugs](references/phase1-bugs.md) | Phase 1 具体 bug 及首次 CLI 调试记录 |
| [CLI 模式](references/cli-patterns.md) | CLI 输出规范与踩坑模式 |
| [续命模式](references/continuation-pattern.md) | LLM 决策注入、演化历史、废弃方案 |

## 工作原则

**重大改动前**：先说明计划 → 等待确认 → 分步执行

1. **简单优于复杂** — 能写函数就不写类
2. **约定优于配置** — 提供合理默认值
3. **渐进式实现** — 先跑起来，再优化，最后重构
4. **测试驱动** — 核心逻辑必须有单元测试覆盖
5. **根因优先** — 修改 bug 必须先找到根因，再根据根因修复。禁止只修表面症状（如加 `except: pass`、在调用方 try/catch 掩盖源头问题）。修复前必须评估对总体架构的影响和副作用。
6. **同类全检** — 修一个方法/文件时，必须搜索并同步修复所有同类代码。例如改 `chat()` 必须看 `chat_stream()`，改工具执行必须看所有工具。禁止"就这一个方法改"。
7. **核心无关 provider** — `core/` 层代码（llm.py, agent.py 等）的注释、变量名、逻辑中禁止出现任何具体 provider 名。Provider 特定行为通过参数化暴露（如 `retry_delays`、`cooldown`），由配置层或 Agent 初始化时传入。
8. **小 patch 优于大替换** — patch 工具只改 3-10 行，不要替换整个方法。patch 前必须用 `read_file(path)` 无参完整读取整个文件，禁止 offset/limit 分页读取后直接 patch。
9. **注释写为什么，不写怎么做** — 代码注释描述设计意图和边界条件（"防死循环"），不描述变更历史（"上次 10 不够"）和操作步骤（"写入文件"）。"上次""昨天"等相对时间词禁止出现在注释中——那是 git commit 的事。硬编码的魔法数字必须可配置或附清晰的语义常量名。改动原因和教训写入 `docs/project-vision/references/` 对应文档。禁止 `write_file` 覆盖整文件——用 `patch`。
10. **input() + 信号整数计数器 = 简洁可靠的两段退出** — 用户按 Ctrl+C 时信号 handler 递增 `exit_count`（0→1→2=退出）。`input()` 阻塞期间连续 Ctrl+C 可累加计数，正常输入后自动复位（手工 `exit_count = 0`）。不要手搓替代方案。\n11. **通解不补丁，可拓展不硬编码** — 用户纠正 bug 时必须问：这是当前场景的补丁还是所有同类问题的通解？通解必须可被其他功能复用、可拓展到新场景。每个\"智能\"功能必须配一个\"我不认识这个\"的 fallback——收录的自动补、未收录的警告不崩溃。新增配置项优先、方法参数化优先、provider 注册表优先。

## Bug 修复流程

1. **写根因陈述** — 一句话描述为什么会出现这个 bug
2. **检查架构影响** — 这个 bug 属于哪个模块？修复会不会影响后续 Phase 规划？
3. **最小修复** — 只改根因涉及的代码行，不顺手改别的
4. **副作用检查** — 会不会让其他地方炸？要不要加 guard/fallback？
5. **验证** — 复现 → 确认修好，不能只靠推测
6. **记录** — 修复后必须立即更新 `bugs.md`（含根因 + 修复方案），并同步到 skill 目录。用户对此零容忍。

## 同步机制

修改 `docs/project-vision/` 下任何文件后，需同步到 agent 的 skill 目录:

```bash
# 同步整个目录到当前 agent 的 skill 目录（根据你的 agent 类型选择路径）
cp -r docs/project-vision <你的agent-skill目录>/
# 示例: opencode → ~/.config/opencode/skills/project-vision/
```

**更新纪律**：每次重大提交后，必须根据提交内容更新 `progress.md`（模块状态变更）、`decisions.md`（新决策）、`architecture.md`（架构变更），然后同步到所有位置。不要在代码变更后留下过期的 skill 文档。

**提交后检查清单**：
- [ ] `progress.md` — 模块状态有无变更？里程碑推进了？
- [ ] `decisions.md` — 有新的架构/技术决策？
- [ ] `lessons.md` — 有值得记录的教训？
- [ ] `bugs.md` — 有新 bug 或修复？
- [ ] `architecture.md` — 目录结构/模块设计有变化？
- [ ] `SKILL.md` 状态行 — 计数是否准确？
- [ ] 同步到 `.opencode/skills/project-vision/` 和 `~/.config/opencode/skills/project-vision/`

## 注意事项

- 保持 MVP 思维，不过度设计
- 每个新功能要回答：用户为什么需要它？
- 优先复用成熟库，遵循 PEP 8
