# Next Focus — 投入方向

> 最后更新: 2026-06-16
> 状态: 决策中

## 决策：Self-Improving Agent Loop（自进化执行）

merco 下一个投入方向锁定为 **Self-Improving Agent Loop**。

## 为什么是这个方向

### 1. 架构复用率最高
| 数据源 | 现状 | Self-Improving 怎么用 |
|--------|------|----------------------|
| `Observer` (`merco/observability/observer.py`) | 已有 11 个 hook 事件 + 计数 | 反馈数据源 |
| `Memory` 双向打通 (SavePipeline + HybridRecaller) | 刚完成 | 沉淀"教训" |
| `HookRegistry` (`merco/hooks/registry.py`) | 完整事件系统 | 触发反馈回路 |
| `SessionStore` (`merco/memory/session_store.py`) | SQLite 持久化 + Fork | 归档"bad case" |
| `Pipeline` 模式 (`merco/core/pipeline.py`) | 成熟 (Recovery / EmptyResponse / Result) | 套用新策略 |

**零新基础设施**，全是用现有管道。

### 2. merco 独家路径
- **三家对标**（hermes / openclaw / opencode）都没有"自进化"作为核心特性
- hermes 的 self-improving 是 fine-tuning（重、需要训练数据）
- merco 可以做 **prompt-level 进化**（轻、即时生效、不破坏模型）
- merco 现有 `观察性报告: ✓ 独有` 是数据底座，Self-Improving 是数据出口

### 3. 不破坏现有架构
- 增量：加一个 `SelfImprover` 订阅 `tool.error` / `conversation.turn` / `llm.chat`
- 不改 Agent 主循环
- 不引入新依赖
- fail-soft 兜底（自进化失败不影响主流程）

### 4. 可见价值
用户用 merco 越久，agent 越"懂自己" — 这是一个**长期复利**的能力。

## 核心机制（草案）

```
┌─────────────────────────────────────────────────────────┐
│ Observer 计数                                            │
│ - tool.error 频率 (按 tool_name 分桶)                   │
│ - llm.chat tokens (cost)                                │
│ - conversation.turn 用户中断率                          │
└─────────────────────────────────────────────────────────┘
                          ↓ 触发
┌─────────────────────────────────────────────────────────┐
│ FeedbackDetector (策略)                                  │
│ - 错误模式识别（连续 N 次同 tool 失败 → 触发）          │
│ - 成本异常（单次 token > 阈值 → 触发）                   │
│ - 用户反复纠正（同一 user message 改 3 次 → 触发）       │
└─────────────────────────────────────────────────────────┘
                          ↓ emit hook
┌─────────────────────────────────────────────────────────┐
│ Improver (新)                                            │
│ - 收集 bad case → 调 LLM 生成"应该怎么做"的 prompt      │
│ - 写到 Memory（key=user_lesson / agent_lesson, source=system）│
│ - 注入 system prompt 的"经验"段                          │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│ Memory / HybridRecaller                                 │
│ 下次 run() → 自动召回 "经验" → 注入 system prompt        │
└─────────────────────────────────────────────────────────┘
```

## 设计原则（必须遵守）

1. **DRY** — 复用 Observer/Memory/Hook，不重新发明
2. **YAGNI** — 不做 fine-tuning、不做 embedding、不做 RL
3. **fail-soft** — Improver 任何步骤失败 → log + 跳过，绝不阻塞主循环
4. **透明性** — 用户能看 `/report` 知道"agent 学到了什么"
5. **可关闭** — `config.self_improver_enabled = True` (默认关，opt-in)
6. **可重置** — `/forget` 经验类 memory

## YAGNI 边界（不做）

- ❌ 模型 fine-tuning（hermes 路线，merco 走 prompt-level）
- ❌ 跨 agent 共享学习（先单 agent 跑通）
- ❌ 经验图谱（实体-关系抽取）
- ❌ RLHF / 奖励模型
- ❌ 自动重写历史 session

## 实施节奏（待细化）

### Phase 1: 观察-反馈链路 (基础)
- FeedbackDetector：识别 3 类触发条件
- Hook 事件：`feedback.detected`
- 简单规则：3 次同 tool error → emit feedback.detected

### Phase 2: Improver 闭环
- 订阅 `feedback.detected`
- 调 LLM 生成"教训 prompt"
- 写入 Memory（source=system，priority 1）
- HybridRecaller 召回注入 system prompt

### Phase 3: 透明化 + 可控
- `/report` 显示"已学习 N 条经验"
- `/lessons` 列出所有经验类 memory
- `config.self_improver_enabled` opt-in
- `/forget` 经验类支持

### Phase 4: 边界 case + 稳定性
- 经验冲突（互相矛盾的 lesson）
- 经验质量低（LLM 生成废话）
- 经验过期（场景变了旧经验反作用）
- 测试覆盖

## 风险

| 风险 | 缓解 |
|------|------|
| LLM 生成的"教训"质量差 | 用真实失败 case 作为 prompt context，让 LLM 看到具体问题 |
| 经验污染主流程 | Improver 异步，失败只 log，不阻塞 agent |
| 经验过期/反作用 | `/lessons` 列出 + `/forget` 手动删除 + 后续可加 TTL |
| 经验无限增长 | 暂无 TTL，靠 `/forget` 手动管理（YAGNI 原则） |
| 误学习（用户纠正其实是 LLM 对的） | opt-in 默认关 + 透明化 + 用户随时能看/删 |

## 关键文件（预想）

```
merco/self_improve/
├── __init__.py
├── detector.py          # FeedbackDetector: 识别触发条件
├── improver.py          # Improver: LLM 生成 lesson → Memory
└── lessons.py           # LessonStore: 经验类 memory 的特殊管理（可选）

merco/core/agent.py      # 启动装配 Improver
merco/observability/observer.py  # 订阅反馈事件 / 报告经验数
merco/core/config.py     # 新增 self_improver_enabled 等字段
cli/commands.py          # /lessons 命令
tests/self_improve/      # 单元 + 集成测试
```

## 决策依据

- 候选 A: Self-Improving Agent Loop ← **选这个**
- 候选 B: Multi-Modal Context 引擎 — scope 大、依赖重，暂缓
- 候选 C: Agent Composition (子 agent 编排) — 工程量大、各家都在做，无差异化

## 下一步

进入 brainstorming skill，产出 spec → plan → 执行
