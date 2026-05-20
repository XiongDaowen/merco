---
name: project-vision
description: OpenMercury project vision, architecture, design decisions, development guidelines, coding standards, milestones, tech stack, and project conventions. 项目愿景、架构设计、开发指南、编码规范、技术决策、里程碑、技术栈。Use when working on OpenMercury: planning features, making architecture decisions, understanding project direction, or implementing code.
---

# OpenMercury 项目愿景

混合型 AI Agent 框架，融合两家主流 Agent 框架的核心优势，构建一个**轻量、高效、可落地**的 Python 智能开发助手。

## 核心目标

1. **杂交优势** — 继承成熟的 Agent 循环机制、Skill 系统、MCP 协议、多代理协作
2. **精简架构** — 移除冗余抽象层，聚焦核心开发场景
3. **Python 原生** — uv/pyproject.toml，asyncio 异步生态
4. **落地优先** — 每个功能有明确使用场景，避免过度工程化

## 当前状态

**Phase 1 完成 → Phase 2 起步** | 19 REAL + 8 PARTIAL + 12 SKELETON + 6 NOT WIRED | 对标 Hermes/OpenClaw/OpenCode | 最后更新: 2026-05-20

## 详细文档

| 文档 | 内容 |
|------|------|
| [项目进展](references/progress.md) | 已完成清单、骨架待实现、里程碑、下一步计划 |
| [架构设计](references/architecture.md) | 模块设计、目录结构、技术栈、参考资料库 |
| [关键决策](references/decisions.md) | 重要决策记录与原因 |
| [开发教训](references/lessons.md) | 犯过的错、反思、以后的规则 |
| [Bug 追踪](references/bugs.md) | 已修复和待修复的 bug |

## 工作原则

**重大改动前**：先说明计划 → 等待确认 → 分步执行

1. **简单优于复杂** — 能写函数就不写类
2. **约定优于配置** — 提供合理默认值
3. **渐进式实现** — 先跑起来，再优化，最后重构
4. **测试驱动** — 核心逻辑必须有单元测试覆盖
5. **根因优先** — 修改 bug 必须先找到根因，再根据根因修复。禁止只修表面症状（如加 `except: pass`、在调用方 try/catch 掩盖源头问题）。修复前必须评估对总体架构的影响和副作用，确保改动兼容项目目标。

## Bug 修复流程

1. **写根因陈述** — 一句话描述为什么会出现这个 bug
2. **检查架构影响** — 这个 bug 属于哪个模块？修复会不会影响后续 Phase 规划？
3. **最小修复** — 只改根因涉及的代码行，不顺手改别的
4. **副作用检查** — 会不会让其他地方炸？要不要加 guard/fallback？
5. **验证** — 复现 → 确认修好，不能只靠推测

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
