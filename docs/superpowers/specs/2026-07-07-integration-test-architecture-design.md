# 集成测试架构设计规范

**状态**: 待审
**创建时间**: 2026-07-07
**目标**: 提升项目集成测试质量，覆盖工具调用、插件系统、技能系统、调度器、快照恢复五大领域

## 一、问题背景

### 1.1 当前现状

- 项目已有部分集成测试（`test_scenarios.py`、`test_todo_subagent.py`、`test_tool_middleware.py` 等）
- 测试覆盖不完整：插件系统、技能系统、调度器、快照恢复四大领域几乎无集成测试
- 现有测试 fixture 简单（单一 `test_agent`），无法支持跨领域场景
- 现有 `MockLLMClient` 只支持"预设响应队列"，复杂场景表达力不足

### 1.2 目标

通过"场景驱动 + 零污染隔离 + 可编程 Mock"的新架构：

1. 覆盖五大领域 38 个集成场景
2. 每个场景独立的环境（snapshot、todo、scheduler、guard、skill_registry 全隔离）
3. 跨领域场景可通过可编程 Mock 灵活表达
4. 不破坏现有测试，渐进式迁移

## 二、架构总览

### 2.1 目录组织

```
tests/integration/
├── __init__.py
├── conftest.py                  # 集成测试入口，挂载顶层 fixture
├── core/                        # 通用测试基础设施
│   ├── __init__.py
│   ├── programmable_mock.py     # 可编程 MockLLMClient + Response DSL
│   ├── scenario.py              # TestScenario 上下文对象
│   └── isolation.py             # 全隔离服务工厂
├── test_tool_scenarios.py       # 领域1：工具调用（9 场景）
├── test_plugin_scenarios.py     # 领域2：插件系统（6 场景）
├── test_skill_scenarios.py      # 领域3：技能系统（7 场景）
├── test_scheduler_scenarios.py  # 领域4：调度器（8 场景）
└── test_snapshot_scenarios.py   # 领域5：快照恢复（8 场景）
```

### 2.2 核心设计原则

| 原则 | 说明 |
|------|------|
| 场景驱动 | 测试按用户场景组织，而非按代码模块 |
| 零污染隔离 | 每个场景所有有状态服务（snapshot/todo/scheduler/guard/skill）独立 |
| 可编程 Mock | MockLLMClient 支持条件分支、动态序列、异常注入 |
| 三层断言 | L1 输出 + L2 中间状态 + L3 副作用，按需选择 |

## 三、核心组件设计

### 3.1 TestScenario 上下文对象

`tests/integration/core/scenario.py`:

```python
@dataclass
class TestScenario:
    # ── 核心组件 ──
    agent: Agent                       # 完整初始化的 Agent
    llm: ProgrammableLLMClient         # 可编程 mock

    # ── 隔离服务（每个场景全新） ──
    snapshot_root: Path                # 快照根目录
    todo_db: Path                      # Todo 数据库
    scheduler: CronScheduler           # 独立调度器
    guard: ToolGuard                   # 独立安全守卫
    skill_registry: SkillRegistry      # 独立技能注册表

    # ── 上下文状态 ──
    tmp_path: Path

    # ── 便捷方法 ──
    async def run(self, user_input: str) -> str: ...
    @property
    def messages(self) -> list[dict]: ...
    @property
    def session(self) -> Session: ...
    @property
    def tool_calls(self) -> list[dict]: ...
```

### 3.2 可编程 MockLLMClient

`tests/integration/core/programmable_mock.py`:

```python
@dataclass
class Response:
    """LLM 响应构造器（DSL）"""
    content: str = ""
    tool_calls: list[dict] = field(default_factory=list)
    error: Exception | None = None
    delay: float = 0.0

    @classmethod
    def content(cls, text: str) -> "Response": ...

    @classmethod
    def tool_call(cls, name: str, arguments: dict) -> "Response": ...

    @classmethod
    def error(cls, exc: Exception) -> "Response": ...


class ProgrammableLLMClient:
    def expect(self, responses: list[Response]) -> "Self": ...
    def expect_sequence(self, fn: Callable[[int], Response]) -> "Self": ...
    def when(self, condition: Callable, response: Response) -> "Self": ...
    @property
    def calls(self) -> list[dict]: ...
```

### 3.3 隔离服务工厂

`tests/integration/core/isolation.py`:

```python
@pytest.fixture
def isolation_services(tmp_path, monkeypatch) -> dict:
    """为每个场景创建独立的有状态服务"""
    # 1. 快照 → tmp_path/snapshots/
    snapshot_root = tmp_path / "snapshots"
    monkeypatch.setattr(snapshot, "SNAPSHOT_DIR", snapshot_root)

    # 2. Todo → tmp_path/todos.db
    todo_db = tmp_path / "todos.db"

    # 3. 调度器 → 独立 CronScheduler
    scheduler = CronScheduler()

    # 4. Guard → 独立 ToolGuard
    guard = ToolGuard()

    # 5. SkillRegistry → 独立实例
    skill_registry = SkillRegistry()

    return {
        "snapshot_root": snapshot_root,
        "todo_db": todo_db,
        "scheduler": scheduler,
        "guard": guard,
        "skill_registry": skill_registry,
    }
```

### 3.4 顶层 Fixture 链

`tests/integration/conftest.py`:

```python
@pytest.fixture
def scenario(
    tmp_path,
    isolation_services,
    programmable_llm,
) -> TestScenario:
    """场景入口 fixture"""
    agent = build_agent(llm=programmable_llm, ...)
    return TestScenario(
        agent=agent,
        llm=programmable_llm,
        tmp_path=tmp_path,
        **isolation_services,
    )
```

## 四、五大领域场景设计

### 4.1 工具调用（9 场景）

`tests/integration/test_tool_scenarios.py`

| 场景 | 描述 |
|------|------|
| test_full_chain_single_tool | user→LLM→tool_call→tool_result→LLM→final |
| test_multi_tool_calls_in_one_turn | 一轮多个 tool_calls |
| test_guard_deny_blocks_tool | guard DENY 阻止工具 |
| test_guard_ask_triggers_confirmation | guard ASK 抛异常 |
| test_guard_allow_passes_through | guard ALLOW 正常 |
| test_tool_not_in_registry | 未注册工具错误 |
| test_tool_execution_exception | 工具异常包装为 tool_error |
| test_write_file_creates_file | 内置 write_file 真实写入 |
| test_edit_file_modifies_content | 内置 edit_file 真实修改 |
| test_bash_executes_real_command | 内置 bash 真实执行 |

### 4.2 插件系统（6 场景）

`tests/integration/test_plugin_scenarios.py`

| 场景 | 描述 |
|------|------|
| test_register_activate_deactivate_full_lifecycle | 完整生命周期 |
| test_all_builtin_plugins_activate | 6 个内置插件同时激活 |
| test_disabled_plugin_not_activated | config 禁用插件 |
| test_unknown_plugin_in_config_ignored | 未知插件忽略 |
| test_plugin_activation_failure_does_not_block_others | 单个失败不阻塞 |
| test_plugin_deactivation_failure_does_not_crash | 停用失败不崩溃 |
| test_activate_emits_plugin_activated_event | 激活事件 |
| test_deactivate_emits_plugin_deactivated_event | 停用事件 |
| test_plugins_share_context | 多插件共享 context |

### 4.3 技能系统（7 场景）

`tests/integration/test_skill_scenarios.py`

| 场景 | 描述 |
|------|------|
| test_skill_view_describe_lists_skills | describe 列出技能 |
| test_skill_view_disabled_when_no_skills | 空注册表时工具不可见 |
| test_skill_view_loads_content_into_context | 技能内容注入 context |
| test_skill_view_long_content_truncated | 超长内容自动截断 |
| test_skill_view_not_found | 技能不存在错误 |
| test_skill_system_not_initialized | 未初始化错误 |
| test_relevant_skills_by_keyword | 关键词匹配 |
| test_skill_view_appears_in_tool_definitions | 工具定义可见 |

### 4.4 调度器（8 场景）

`tests/integration/test_scheduler_scenarios.py`

| 场景 | 描述 |
|------|------|
| test_job_executes_on_schedule | 时间到达执行 |
| test_wildcard_cron_matches_any_time | 通配符匹配 |
| test_async_handler_awaited | async handler |
| test_sync_handler_called | sync handler |
| test_multiple_jobs_concurrent_execution | 多任务并发 |
| test_jobs_update_independently | 独立更新 run_count |
| test_failing_job_does_not_block_others | 异常隔离 |
| test_disabled_job_skipped | 禁用任务跳过 |
| test_re_enabled_job_runs | 重新启用执行 |
| test_list_jobs_returns_metadata | 列表返回元数据 |
| test_remove_job | 移除任务 |

### 4.5 快照恢复（8 场景）

`tests/integration/test_snapshot_scenarios.py`

| 场景 | 描述 |
|------|------|
| test_edit_file_creates_snapshot | 编辑创建快照 |
| test_write_file_creates_snapshot | 写入创建快照 |
| test_revert_single_snapshot_restores_only_that_file | 单点回滚 |
| test_revert_all_restores_all_files | 全部回滚 |
| test_revert_all_clears_session_file | 回滚后清理 |
| test_history_lists_all_snapshots | 历史查询 |
| test_history_for_nonexistent_session | 不存在会话 |
| test_different_sessions_have_independent_history | session 隔离 |

## 五、断言规范

### 三层断言

```python
async def test_example(scenario):
    # ── 1. 准备 ──
    scenario.llm.expect([Response.content("OK")])

    # ── 2. 执行 ──
    result = await scenario.run("hello")

    # ── 3. 断言 ──
    # L1（必选）：最终输出
    assert "OK" in result

    # L2（按需）：中间状态
    assert scenario.messages[-1]["role"] == "assistant"
    assert scenario.tool_calls == []

    # L3（按需）：副作用
    assert scenario.snapshot_root.exists()
    assert len(scenario.session.messages) == 2
```

## 六、与现有测试的关系

| 现有测试 | 处置 |
|----------|------|
| test_scenarios.py | 保留核心场景（基础对话、工具调用链、会话持久化），删除与新架构重复部分 |
| test_todo_subagent.py | 保留 todo 创建/派发核心测试，删除冗余 |
| test_tool_middleware.py | 保留（作为单元测试级别的工具中间件测试） |
| 其他 test_*.py | 保留不动 |

## 七、实施计划

1. 创建 `core/` 目录与基础设施（programmable_mock、scenario、isolation）
2. 创建 `conftest.py` 顶层 fixture
3. 实施 test_tool_scenarios.py（9 场景）
4. 实施 test_plugin_scenarios.py（6 场景）
5. 实施 test_skill_scenarios.py（7 场景）
6. 实施 test_scheduler_scenarios.py（8 场景）
7. 实施 test_snapshot_scenarios.py（8 场景）
8. 现有测试迁移/清理
9. 全量回归验证

## 八、成功标准

- 五大领域 38 个场景全部通过
- 与现有测试无冲突，可并行运行
- 每个场景执行时间 < 5 秒
- 不依赖真实 LLM API（除非显式标记为 E2E）
- 失败时可定位到具体阶段
