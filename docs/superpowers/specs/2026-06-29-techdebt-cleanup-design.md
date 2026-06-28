# Phase 4：Phase 3 技术债全清 — 设计规格

> 日期: 2026-06-28
> 前置: Phase 3 全部完成

## 背景

Phase 3 建立了 `Agent.create(...)` async factory，并迁移了 6 个内置插件。但迁移过程中留下了三层技术债：

1. **Agent.__init__ 双路径**
   - `_defer_plugin_init` 布尔开关，在同一个 `__init__` 里分叉两套行为
   - legacy 路径：`Observer(self.hooks)` 直构、`_restore_context()` 在 `__init__` 内执行、`activate_all()` fire-and-forget
   - factory 路径：`observer = None`、`_restore_context()` 延后执行、`_initialize_async_plugins()` 确定性激活

2. **CLI sync 路径**
   - `_setup_agent` 是 sync 函数，直接用 `Agent(...)` legacy 路径
   - 手动创建 SkillRegistry + 向 SkillViewTool 注入作为 "fire-and-forget 不可靠" 的兜底

3. **测试 fixture 走 legacy**
   - `tests/conftest.py::test_agent` 用 `Agent(...)` 而非 `Agent.create(...)`
   - 大部分测试实际上在 legacy 路径跑，没有验证 factory 路径

用户选择"全清"：一次性删除双路径，`Agent.create()` 成为唯一初始化入口。

## 目标

1. 删除 `_defer_plugin_init` 及其所有 gate。
2. `Agent.__init__` 只做同步初始化，不做任何异步操作。
3. `Agent.create()` 是唯一完整初始化路径。
4. CLI `_setup_agent` 改为 async，使用 `Agent.create()`。
5. `tests/conftest.py::test_agent` 改为 async fixture，使用 `Agent.create()`。
6. 所有使用 `test_agent` 的测试适配 async。
7. 删除 CLI 中的手动 SkillRegistry 创建 + SkillViewTool 注入（SkillPlugin 负责）。

## 非目标

- 不改 `Agent.run()` / `Agent._agent_loop()` 逻辑。
- 不改任何插件实现。
- 不改 `PluginManager`。
- 不改 `SubAgentManager`（已在 3.2 迁移）。
- 不改 MCP / Web / Scheduler。
- 不新增功能。

---

## 设计

### 1. Agent.__init__ — 只做同步初始化

**当前签名：**
```python
def __init__(self, config: MercoConfig, tool_registry=None, _defer_plugin_init: bool = False):
```

**清理后：**
```python
def __init__(self, config: MercoConfig, tool_registry=None):
```

**删除块：**

| 行 | 内容 | 
|---|---|
| `_defer_plugin_init` 参数 | 不再需要 |
| `Observer(self.hooks)` legacy 直构 | 始终在 ObservabilityPlugin 激活时创建 |
| `_restore_context()` 调用在 `__init__` 中 | 始终在 `_initialize_async_plugins` 中调用 |
| `activate_all()` 整块 | 始终在 `_initialize_async_plugins` 中调用 |

**保留不变：**
- `HookRegistry()` 创建
- Guard、Middleware 装配
- Session store、pipelines、prompt_builder、memory、profile registry、loop_policies 初始化
- `PluginContext` / `PluginManager` 构建
- 所有 7 个内置插件 `register()`

**初始化为 None 的属性（由插件补充）：**
```python
self.observer = None
self.skill_registry = None
self.todo_manager = None
self.sub_agent_manager = None
self.mcp_manager = None
```

### 2. Agent.create() — 唯一初始化路径

保持不变：

```python
@classmethod
async def create(cls, config: MercoConfig, tool_registry=None) -> "Agent":
    agent = cls(config=config, tool_registry=tool_registry)
    await agent._initialize_async_plugins()
    return agent
```

激活顺序不变：

```text
observability → sync observer → restore_context → skills → mcp → subagent → web → scheduler → activate_all
```

### 3. CLI 改 async

**`_setup_agent` 变为 async：**

```python
async def _setup_agent(config_path, model, api_key, debug):
    ...
    # 删除手动 SkillRegistry 创建 + SkillViewTool 注入（198-207）
    # 删除 agent.skill_registry = skill_registry 后备（214）
    
    agent = await Agent.create(config=cfg, tool_registry=tool_registry)
    ...
    return agent, dashboard, config_source
```

**`main_callback` / `run_cmd` 用 `asyncio.run()` 桥接：**

```python
@app.callback(invoke_without_command=True)
def main_callback(...):
    if ctx.invoked_subcommand is not None:
        return
    agent, dashboard, config_source = asyncio.run(_setup_agent(config, model, api_key, debug))
    run_repl(agent, dashboard, config_source)
```

### 4. test_agent fixture 改 async

**`tests/conftest.py`：**

```python
@pytest.fixture
async def test_agent(monkeypatch, tmp_path):
    ...
    agent = await Agent.create(config=cfg, tool_registry=reg)
    return agent
```

**所有使用 `test_agent` 的测试：**

需要用 `@pytest.mark.asyncio` + `async def`。约 50+ 个测试文件涉及。

---

## 测试策略

### CLI smoke test

- `tests/cli/test_cli_help.py` 继续通过（不改 `test_agent` 路径，测试直接 invoke CLI）

### Agent.create 集成测试

- 已有 `test_agent_create_*` 系列测试（3.1-3.6 累积），全部保留

### test_agent fixture 迁移

- 每个使用 `test_agent` 的测试加 `@pytest.mark.asyncio` + `async def`
- 确保 `await Agent.create(...)` fixture 在测试中正常运作

### 回归测试

全量 `tests/`。

---

## 风险与约束

1. **大量测试需加 async**
   - ~50+ 个测试文件，每个测试加 `@pytest.mark.asyncio` 和 `async def`。
   - 纯机械迁移，不改变测试断言。

2. **asyncio.run() 在 Typer callback 中**
   - `main_callback` 和 `run_cmd` 是 Typer 的 sync callback。
   - `asyncio.run()` 在 sync 函数里创建新 event loop 是安全的。

3. **SubAgentManager._create_sub_agent 已用 Agent.create()**
   - 3.2 已迁移，不需要改。

4. **删除 `_defer_plugin_init` 后**
   - 之前的 `if not _defer_plugin_init:` 门控路径不再有。
   - 确保 `Agent.create()` 调用 `cls(...)` 时不再传废弃参数。

## 用户确认的设计选择

- 范围：**全清**
- Agent.__init__ 不再执行任何 async 操作
- Agent.create() 是唯一初始化入口
- CLI + test_agent 全部迁
- 删除所有遗留的 fire-and-forget / legacy observer / 双路径代码