# Phase 3.4：SubAgentPlugin + CLI e2e Smoke Test 设计规格

> 日期: 2026-06-28
> 基于: `docs/project-vision/references/architecture-refactor-plan.md`
> 前置: Phase 3.1 + 3.2 + 3.3 已完成

## 背景

当前 `Agent.__init__` 中：

```python
self.todo_manager = TodoManager(f"{config.memory_path}/../todos.db")
self.sub_agent_manager = SubAgentManager(self, self.agent_profiles)
```

并紧跟一个 TaskTool 特殊注入：

```python
task_tool = self.tool_registry.get("task")
if task_tool:
    task_tool._todo_manager = self.todo_manager
    task_tool._sub_agent_manager = self.sub_agent_manager
```

`SubAgentManager` 持有 `parent` Agent 引用、依赖 `agent_profiles` registry，并通过 `TaskTool` 派发。这是 Phase 3 中最大的一块「特殊化代码」，最需要插件化。

同时整个 Phase 3 缺少真实启动路径的端到端测试。单元测试和 mock LLM 集成测试都过，但 `merco run --help` 启动路径从未验证过，导致 3.2 删 `skill_registry` 参数后实际启动直接抛 `TypeError`，但所有测试都过。

用户要求 3.4 同时加一个能验证 `merco run --help` 的 e2e 测试。

## 目标

1. 新增 `SubAgentPlugin`，负责创建 `TodoManager` + `SubAgentManager` + TaskTool 注入。
2. `PluginContext` 增加 `todo_manager` / `sub_agent_manager` 字段（已是 None 默认；本轮只补 subagent 注入逻辑）。
3. `Agent.create(...)` 激活 `subagent` 插件。
4. `Agent.__init__` 移除 TodoManager / SubAgentManager 硬初始化。
5. TaskTool 注入移到 SubAgentPlugin。
6. 新增一个能验证 `merco run --help` 启动成功的 e2e CLI smoke test。
7. CLI 入口 `cli/main.py` 不再传 `skill_registry` / `todo_manager` / `sub_agent_manager` 等参数（继续清理 3.2 之后遗留的 CLI 特殊代码）。

## 非目标

- 不迁移 Web / Scheduler。
- 不改 SubAgentManager / TodoManager 内部行为。
- 不改 TaskTool。
- 不在本轮重构 CLI 为 async；CLI 仍为 sync `_setup_agent` + fire-and-forget plugin 激活。
- 不实现完整 e2e 启动链路测试；只验证 `merco run --help` 能成功启动并输出 Usage。

---

## 设计

### 1. SubAgentPlugin

新增 `merco/plugins/builtin/subagent/plugin.py`：

```python
class SubAgentPlugin(Plugin):
    name = "subagent"
    version = "1.0.0"
    description = "Creates todo manager, sub-agent manager, and wires TaskTool"

    async def activate(self, ctx):
        from merco.todo.manager import TodoManager
        from merco.agents.subagent import SubAgentManager

        todo_manager = TodoManager(f"{ctx.config.memory_path}/../todos.db")
        sub_agent_manager = SubAgentManager(ctx.agent, ctx.agent_profiles)

        ctx.todo_manager = todo_manager
        ctx.sub_agent_manager = sub_agent_manager
        if ctx.agent is not None:
            ctx.agent.todo_manager = todo_manager
            ctx.agent.sub_agent_manager = sub_agent_manager

        task_tool = ctx.tool_registry.get("task")
        if task_tool is not None:
            if hasattr(task_tool, "_todo_manager"):
                task_tool._todo_manager = todo_manager
            if hasattr(task_tool, "_sub_agent_manager"):
                task_tool._sub_agent_manager = sub_agent_manager
```

### 2. Agent 初始化变化

#### 2.1 `Agent.__init__`

删除：

```python
# ── Todo + SubAgent 系统 ──
from merco.todo.manager import TodoManager
from merco.agents.subagent import SubAgentManager

self.todo_manager = TodoManager(f"{config.memory_path}/../todos.db")
self.sub_agent_manager = SubAgentManager(self, self.agent_profiles)
```

替换为：

```python
# Todo + SubAgent 由 SubAgentPlugin 激活时创建
self.todo_manager = None
self.sub_agent_manager = None
```

同时删除 TaskTool 特殊注入段：

```python
# 注入到 TaskTool（全局 tool_registry 中的 TaskTool 实例）
task_tool = self.tool_registry.get("task")
if task_tool:
    task_tool._todo_manager = self.todo_manager
    task_tool._sub_agent_manager = self.sub_agent_manager
```

#### 2.2 `_initialize_async_plugins()` 顺序

```text
1. await plugin_manager.activate("observability")
2. sync agent.observer
3. _restore_context()
4. await plugin_manager.activate("skills")
5. await plugin_manager.activate("mcp")
6. await plugin_manager.activate("subagent")
7. await plugin_manager.activate_all()
```

#### 2.3 注册 SubAgentPlugin

```python
self.plugin_manager.register(ObservabilityPlugin())
self.plugin_manager.register(SkillPlugin())
self.plugin_manager.register(MCPPlugin())
self.plugin_manager.register(SubAgentPlugin())
self.plugin_manager.register(SuperpowerPlugin())
```

### 3. CLI 清理

`cli/main.py:209` 之外，仍有：

- `cli/main.py:198-207` 手动构建 `SkillRegistry` 并注入 `SkillViewTool`（3.2 后由 SkillPlugin 处理）
- `cli/main.py:209-211` 调 `Agent(...)` 构造

由于 CLI 是 sync 且当前 `_setup_agent` 不能直接调 `Agent.create()`，本轮采取最小修复：

1. 删除 `skill_registry=skill_registry` 参数（已在 5c57bc0 修过）
2. 保留 `install_builtin_skills()` 和手动 skill loading（作为 legacy 路径的兜底，因为 fire-and-forget 插件激活可能有时序问题）
3. 保留 `agent.skill_registry = skill_registry` 后备赋值（5c57bc0 已加）

**不**在本轮把 CLI 改为 `Agent.create()`。这是单独的设计项。

### 4. e2e CLI Smoke Test

#### 4.1 测试位置

`tests/cli/test_cli_help.py`

#### 4.2 测试用例

`merco run --help` / `merco --help` / `merco init --help` 三个 smoke test，验证 Typer 引导不抛异常并输出 Usage。

```python
"""CLI smoke tests — 验证 `merco run --help` 启动不因 import/构造错误失败。

Phase 3 经验教训：单元 + mock LLM 集成测试不能覆盖 import-time 的代码
错误（如 `cli/main.py` 仍在传已删的 `skill_registry` 参数）。本测试触发
真实 CLI 启动路径，但不调用 LLM，只验证 Typer 应用能正确引导。
"""

import pytest
from typer.testing import CliRunner


@pytest.fixture
def cli_runner():
    return CliRunner()


def test_merco_run_help_succeeds(cli_runner):
    """`merco run --help` 启动不抛异常、exit code 0、输出 Usage"""
    from cli.main import app

    result = cli_runner.invoke(app, ["run", "--help"])

    assert result.exit_code == 0, f"stdout={result.stdout!r} stderr={result.stderr or ''!r}"
    assert "Usage:" in result.stdout


def test_merco_root_help_succeeds(cli_runner):
    """`merco --help` 启动不抛异常"""
    from cli.main import app

    result = cli_runner.invoke(app, ["--help"])

    assert result.exit_code == 0, f"stderr={result.stderr or ''!r}"
    assert "Usage:" in result.stdout


def test_merco_init_help_succeeds(cli_runner):
    """`merco init --help` 启动不抛异常"""
    from cli.main import app

    result = cli_runner.invoke(app, ["init", "--help"])

    assert result.exit_code == 0
    assert "Usage:" in result.stdout
```

#### 4.3 已知风险

- CLI 入口 `cli/main.py` 仍在 sync `Agent()` 路径，fire-and-forget 插件激活有 race condition。
- e2e 测试只验证 CLI 启动 + Typer help 输出，**不**验证业务功能（agent.run()）。
- 未来如果用户输入实际 prompt，CLI 仍可能因 sync `Agent()` 路径遗留问题失败。

### 5. SubAgentPlugin 单测

`tests/plugins/test_subagent_plugin.py`：

- activate 后 `ctx.todo_manager` 是 `TodoManager`
- `ctx.sub_agent_manager` 是 `SubAgentManager`
- `ctx.agent.todo_manager` / `ctx.agent.sub_agent_manager` 同步
- `ctx.tool_registry` 包含 `task` 时，注入成功
- `ctx.tool_registry` 不含 `task` 时安全跳过

### 6. Agent.create 集成测试

`tests/core/test_agent.py`：

- `await Agent.create(...)` 后 `agent.todo_manager` 是 `TodoManager`
- `agent.sub_agent_manager` 是 `SubAgentManager`
- `agent.plugin_manager.active_plugins` 包含 `subagent`
- `task` 工具的 `_todo_manager` / `_sub_agent_manager` 被注入

### 7. Test 适配

3.2 已将 `SubAgentManager._create_sub_agent` 改为 async，并使用 `await Agent.create(...)`。本轮不重做这部分。

`tests/agents/test_subagent.py` 和 `tests/agents/test_subagent_profile.py` 已具备 async 适配。

`SubAgentManager` 内部不需修改，因为它不创建 `TodoManager` / `sub_agent_manager` 本身（这些来自 SubAgentPlugin）。

### 8. 回归测试

- `tests/cli/test_cli_help.py`（新增）
- `tests/plugins/test_subagent_plugin.py`（新增）
- `tests/core/test_agent.py`
- `tests/agents/test_subagent.py` / `test_subagent_profile.py`
- `tests/integration/test_todo_subagent.py`

---

## 风险与约束

1. **CLI 仍是 sync 路径**
   - `merco run --help` 只验证 Typer 引导，不验证真实 prompt 流程。
   - 未来需单独重构 CLI 为 `await Agent.create(...)`。

2. **e2e 测试覆盖率有限**
   - 只防 import-time 错误，不防运行时错误。
   - 应在本轮之后再补充端到端测试（mock 实际 prompt）。

3. **legacy `Agent(...)` 路径下 SubAgent 不存在**
   - `agent.todo_manager` 和 `agent.sub_agent_manager` 在 legacy path 初始为 None。
   - 测试 fixture 如果调 TaskTool 会失败。
   - 这些 fixture 应改为 `await Agent.create(...)`。

4. **fire-and-forget 时序**
   - legacy `Agent(...)` 路径下 activate_all() 是 fire-and-forget。
   - e2e help 测试不调 prompt，规避时序。

5. **TaskTool 注入顺序**
   - SubAgentPlugin 依赖 `ctx.tool_registry` 已有 `task` 工具。
   - 工具必须先于 SubAgentPlugin 注册。SkillPlugin/MCPPlugin 不需要 task 工具。

## 用户确认的设计选择

- 3.4 范围：**彻底迁移**
- 增加：**e2e CLI smoke test**（验证 `merco run --help`）
- 实施顺序：e2e smoke test 先做，SubAgentPlugin 后做

## 自审结论

- `SubAgentPlugin` 持有 parent agent 引用，通过 `ctx.agent` 读取。
- `ctx.tool_registry.get("task")` 用 `hasattr` 防御，与 3.1/3.2/3.3 一致。
- CLI 仍是 sync `Agent()`，不本轮重构；e2e smoke test 只覆盖 Typer 引导。
- 后续要把 CLI 改为 `await Agent.create(...)`，单独做。
