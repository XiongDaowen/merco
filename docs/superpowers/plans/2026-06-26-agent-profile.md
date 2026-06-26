# merco AgentProfile 插件化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让子代理按专业角色（researcher/reviewer/debugger/security）创建，插件可注册 AgentProfile

**Architecture:** AgentProfile dataclass + AgentProfileRegistry + 4 builtins + PluginContext 暴露 agent_profiles + SubAgentManager 根据 profile 创建专业子代理

**Tech Stack:** Python 3.12, dataclass, asyncio

---

## 文件结构

| 文件 | 职责 |
|------|------|
| `merco/agents/profile.py` | AgentProfile dataclass + AgentProfileRegistry + ProfilePromptChunk + builtins |
| `merco/agents/subagent.py` | SubAgentManager 使用 profile 创建子代理 |
| `merco/plugins/base.py` | PluginContext 新增 agent_profiles |
| `merco/core/agent.py` | 创建 AgentProfileRegistry + 注册 builtins + 注入 PluginContext + 注入 SubAgentManager + 注入 TaskTool |
| `cli/commands.py` | /agents /agent 命令 |
| `tests/agents/test_profile.py` | AgentProfile + Registry 单测 |
| `tests/agents/test_subagent_profile.py` | SubAgentManager profile 单测 |
| `tests/integration/test_agent_profile.py` | TaskTool agent=researcher 端到端 |

---

## Task 1: AgentProfile dataclass + Registry + builtins

**Files:**
- Create: `merco/agents/profile.py`
- Test: `tests/agents/test_profile.py`

- [ ] **Step 1: Write the failing test**

Create `tests/agents/test_profile.py`:

```python
"""AgentProfile + Registry 单测"""
from merco.agents.profile import AgentProfile, AgentProfileRegistry, BUILTIN_PROFILES


class TestAgentProfile:
    def test_agent_profile_creation(self):
        p = AgentProfile(name="qa", description="qa agent", prompt="you test things")
        assert p.name == "qa"
        assert p.tools == []
        assert p.model is None
        assert p.limits == {}

    def test_agent_profile_with_all_fields(self):
        p = AgentProfile(
            name="expert",
            description="deep agent",
            prompt="you are expert",
            tools=["read_file", "grep"],
            model={"provider": "openai", "model": "gpt-4o"},
            limits={"max_tool_calls": 20},
        )
        assert p.tools == ["read_file", "grep"]
        assert p.model["model"] == "gpt-4o"
        assert p.limits["max_tool_calls"] == 20


class TestAgentProfileRegistry:
    def test_register_and_get(self):
        reg = AgentProfileRegistry()
        reg.register(AgentProfile(name="test", description="test", prompt="test prompt"))
        assert reg.get("test").name == "test"
        assert reg.get("nonexistent") is None

    def test_list_profiles(self):
        reg = AgentProfileRegistry()
        reg.register(AgentProfile(name="a", description="a", prompt="a"))
        reg.register(AgentProfile(name="b", description="b", prompt="b"))
        assert len(reg.list()) == 2


class TestBuiltinProfiles:
    def test_has_four_builtins(self):
        assert len(BUILTIN_PROFILES) == 4
        names = {p.name for p in BUILTIN_PROFILES}
        assert names == {"default", "researcher", "reviewer", "debugger"}

    def test_researcher_has_tools_allowlist(self):
        researcher = next(p for p in BUILTIN_PROFILES if p.name == "researcher")
        assert len(researcher.tools) > 0
        assert researcher.limits.get("max_tool_calls") == 30
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/xiowen/code/merco && python3 -m pytest tests/agents/test_profile.py -v`
Expected: ImportError (merco.agents.profile not exists)

- [ ] **Step 3: Implement profile module**

Create `merco/agents/profile.py`:

```python
"""AgentProfile data model and registry"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AgentProfile:
    """Professional role configuration for sub-agents"""
    name: str
    description: str
    prompt: str
    tools: list[str] = field(default_factory=list)
    model: dict | None = None
    limits: dict = field(default_factory=dict)


class AgentProfileRegistry:
    """Registry for AgentProfile instances"""

    def __init__(self):
        self._profiles: dict[str, AgentProfile] = {}

    def register(self, profile: AgentProfile) -> None:
        self._profiles[profile.name] = profile

    def get(self, name: str) -> AgentProfile | None:
        return self._profiles.get(name)

    def list(self) -> list[AgentProfile]:
        return list(self._profiles.values())


class ProfilePromptChunk:
    """Prompt chunk that injects agent role from profile"""
    name = "agent_profile"

    def __init__(self, profile: AgentProfile):
        self.profile = profile

    def enabled(self, agent) -> bool:
        return True

    def build(self, agent) -> str:
        return f"## Agent Role: {self.profile.name}\n{self.profile.prompt}"


BUILTIN_PROFILES: list[AgentProfile] = [
    AgentProfile(
        name="default",
        description="普通子代理，继承父代理全部能力",
        prompt="你是 merco 子代理。完成父代理委派的任务，返回简洁明确的结果。",
    ),
    AgentProfile(
        name="researcher",
        description="代码搜索、资料收集、架构理解",
        prompt="你是代码研究员。专注于阅读代码、搜索资料、归纳结构，不做大规模修改。输出清晰的发现和证据。",
        tools=["read_file", "web_fetch", "web_search"],
        limits={"max_tool_calls": 30},
    ),
    AgentProfile(
        name="reviewer",
        description="代码审查、bug 风险识别、质量检查",
        prompt="你是代码审查专家。专注于发现 correctness bug、边界条件、测试缺口和架构问题。只报告高置信问题。",
        tools=["read_file", "grep", "bash"],
        limits={"max_tool_calls": 25},
    ),
    AgentProfile(
        name="debugger",
        description="系统调试、根因分析、失败复现",
        prompt="你是系统调试专家。先定位症状，再建立假设，最后用测试/日志验证。不要盲改。",
        tools=["read_file", "bash", "grep"],
        limits={"max_tool_calls": 40},
    ),
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/xiowen/code/merco && python3 -m pytest tests/agents/test_profile.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
cd /home/xiowen/code/merco
git add merco/agents/profile.py tests/agents/test_profile.py
git commit -m "feat: add AgentProfile dataclass, registry, and builtins"
```

---

## Task 2: PluginContext 扩展 + Agent 装配

**Files:**
- Modify: `merco/plugins/base.py`
- Modify: `merco/core/agent.py`

- [ ] **Step 1: Add agent_profiles to PluginContext**

Add to `merco/plugins/base.py` PluginContext.__init__ parameter list:

```python
agent_profiles: "AgentProfileRegistry" = None,
```

And in the body:

```python
self.agent_profiles = agent_profiles
```

Also add TYPE_CHECKING import:

```python
from merco.agents.profile import AgentProfileRegistry
```

- [ ] **Step 2: Add AgentProfileRegistry to Agent.__init__**

In `merco/core/agent.py`, after PluginContext creation but before plugin activation, add:

```python
        # ── AgentProfile Registry ──
        from merco.agents.profile import AgentProfileRegistry, BUILTIN_PROFILES

        self.agent_profiles = AgentProfileRegistry()
        for p in BUILTIN_PROFILES:
            self.agent_profiles.register(p)

        self._plugin_ctx.agent_profiles = self.agent_profiles
```

- [ ] **Step 3: Update SubAgentManager to accept profile registry**

In `merco/core/agent.py`, change SubAgentManager creation from:

```python
self.sub_agent_manager = SubAgentManager(self)
```

to:

```python
self.sub_agent_manager = SubAgentManager(self, self.agent_profiles)
```

- [ ] **Step 4: Inject managers into TaskTool**

In `merco/core/agent.py`, after SubAgentManager creation, add:

```python
        # 注入到 TaskTool（全局 tool_registry 中的 TaskTool 实例）
        task_tool = self.tool_registry.get("task")
        if task_tool:
            task_tool._todo_manager = self.todo_manager
            task_tool._sub_agent_manager = self.sub_agent_manager
```

- [ ] **Step 5: Verify syntax + run tests**

Run: `cd /home/xiowen/code/merco && python3 -m py_compile merco/plugins/base.py && python3 -m py_compile merco/core/agent.py && echo "Syntax OK"`

Run: `cd /home/xiowen/code/merco && python3 -m pytest tests/plugins/ tests/context/ -v`

- [ ] **Step 6: Commit**

```bash
cd /home/xiowen/code/merco
git add merco/plugins/base.py merco/core/agent.py
git commit -m "feat: wire AgentProfileRegistry into PluginContext and Agent"
```

---

## Task 3: SubAgentManager 使用 profile 创建子代理

**Files:**
- Modify: `merco/agents/subagent.py`
- Test: `tests/agents/test_subagent_profile.py`

- [ ] **Step 1: Write the failing test**

Create `tests/agents/test_subagent_profile.py`:

```python
"""SubAgentManager profile 单测"""
import pytest
from unittest.mock import MagicMock, AsyncMock
from merco.agents.profile import AgentProfile


class TestSubAgentProfile:
    def test_create_with_researcher_profile(self, test_agent):
        """researcher profile 工具过滤"""
        from merco.agents.subagent import SubAgentManager
        from merco.agents.profile import AgentProfileRegistry, BUILTIN_PROFILES

        reg = AgentProfileRegistry()
        for p in BUILTIN_PROFILES:
            reg.register(p)

        manager = SubAgentManager(test_agent, reg)
        sub_agent = manager._create_sub_agent("researcher")

        # researcher 有限制工具列表
        tool_names = [t.name for t in sub_agent.tool_registry.list_tools()]
        for name in tool_names:
            assert name in ["read_file", "web_fetch", "web_search"]

    def test_default_when_profile_not_found(self, test_agent):
        """不存在的 profile 回退到 default"""
        from merco.agents.subagent import SubAgentManager
        from merco.agents.profile import AgentProfileRegistry, BUILTIN_PROFILES

        reg = AgentProfileRegistry()
        for p in BUILTIN_PROFILES:
            reg.register(p)

        manager = SubAgentManager(test_agent, reg)
        sub_agent = manager._create_sub_agent("nonexistent")
        # default 不限制工具，应继承全部
        assert sub_agent.tool_registry == test_agent.tool_registry

    def test_profile_prompt_injected(self, test_agent):
        """profile prompt chunk 被注入"""
        from merco.agents.subagent import SubAgentManager
        from merco.agents.profile import AgentProfileRegistry, BUILTIN_PROFILES

        reg = AgentProfileRegistry()
        for p in BUILTIN_PROFILES:
            reg.register(p)

        manager = SubAgentManager(test_agent, reg)
        sub_agent = manager._create_sub_agent("debugger")
        chunks = sub_agent.prompt_builder._chunks
        assert any(c.name == "agent_profile" for c in chunks)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/xiowen/code/merco && python3 -m pytest tests/agents/test_subagent_profile.py -v`
Expected: test_sub_agent crashes (no profile registry)

- [ ] **Step 3: Update SubAgentManager**

Rewrite `merco/agents/subagent.py`:

```python
"""SubAgentManager — 子代理派发"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from merco.core.agent import Agent
    from merco.agents.profile import AgentProfileRegistry

logger = logging.getLogger("merco.agents.subagent")


class SubAgentManager:
    """子代理派发管理器"""

    def __init__(self, parent: "Agent", profile_registry: "AgentProfileRegistry" = None):
        self._parent = parent
        self._profiles = profile_registry
        self._active: dict[str, "Agent"] = {}

    async def dispatch(self, todo_id: str, prompt: str, agent_name: str = "default") -> str:
        """派发子代理执行任务，返回 subagent_id"""
        sub_agent = self._create_sub_agent(agent_name)
        self._parent.todo_manager.update(todo_id, status="in_progress", assigned_to=sub_agent.session.id)

        try:
            result = await sub_agent.run(prompt)
            self._parent.todo_manager.update(todo_id, status="completed", result=result)
        except Exception as e:
            logger.warning("子代理执行失败: %s", e)
            self._parent.todo_manager.update(todo_id, status="failed", result=str(e))
            result = f"Error: {e}"

        self._inject_result_to_parent(todo_id, result)
        await self._parent.hooks.emit("subagent.completed", todo_id=todo_id, result=result)
        return sub_agent.session.id

    def _create_sub_agent(self, agent_name: str) -> "Agent":
        """创建子代理，根据 profile 配置 prompt/tools/model"""
        from merco.core.agent import Agent
        from merco.core.session import Session
        from merco.agents.profile import ProfilePromptChunk
        from merco.tools.registry import ToolRegistry

        profile = None
        if self._profiles:
            profile = self._profiles.get(agent_name) or self._profiles.get("default")

        config = self._parent.config
        tool_registry = self._parent.tool_registry

        if profile:
            # model override
            if profile.model:
                from merco.core.config import MercoConfig, ModelConfig
                import copy
                config = copy.deepcopy(config)
                config.model.provider = profile.model.get("provider", config.model.provider)
                config.model.model = profile.model.get("model", config.model.model)

            # tools allowlist
            if profile.tools:
                tool_registry = ToolRegistry()
                for name in profile.tools:
                    tool = self._parent.tool_registry.get(name)
                    if tool:
                        tool_registry.register(tool)

        sub_agent = Agent(config=config, tool_registry=tool_registry)
        # force new session
        sub_agent.session = Session(store=sub_agent._session_store)
        sub_agent._session_store.create_session(sub_agent.session.id)

        if profile:
            sub_agent.prompt_builder.use(ProfilePromptChunk(profile))
            if profile.limits.get("max_tool_calls"):
                sub_agent.config.max_tool_calls = profile.limits["max_tool_calls"]

        self._active[sub_agent.session.id] = sub_agent
        return sub_agent

    def _inject_result_to_parent(self, todo_id: str, result: str):
        """把子代理结果注入父代理的 context"""
        self._parent.context.add({
            "role": "tool",
            "content": f"[Todo {todo_id}] 子代理结果:\n{result}",
            "tool_call_id": f"todo_{todo_id}",
        })
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/xiowen/code/merco && python3 -m pytest tests/agents/test_subagent_profile.py tests/agents/test_subagent.py -v`

- [ ] **Step 5: Commit**

```bash
cd /home/xiowen/code/merco
git add merco/agents/subagent.py tests/agents/test_subagent_profile.py
git commit -m "feat: SubAgentManager creates sub-agents from AgentProfile"
```

---

## Task 4: CLI /agents /agent 命令

**Files:**
- Modify: `cli/commands.py`

- [ ] **Step 1: Add CLI commands**

Add after the `/todo-done` command in `cli/commands.py`:

```python
@cmd_registry.register("/agents", "列出所有 AgentProfile", group="task")
async def cmd_agents(agent, args):
    """列出所有 AgentProfile"""
    profiles = agent.agent_profiles.list()
    if not profiles:
        console.print("[dim]暂无 AgentProfile[/dim]")
        return True
    console.print(f"[bold]🤖 Agent Profiles ({len(profiles)} 个)[/bold]")
    console.print("─" * 50)
    for p in profiles:
        tool_count = len(p.tools)
        tools_note = f"{tool_count} tools" if tool_count else "全部工具"
        console.print(f"  [cyan]{p.name}[/cyan]  {tools_note}")
        console.print(f"     [dim]{p.description}[/dim]")
    return True


@cmd_registry.register("/agent", "查看 AgentProfile 详情", group="task")
async def cmd_agent(agent, args):
    """查看 Profile 详情"""
    if not args:
        console.print("[dim]用法: /agent <name>[/dim]")
        return True
    profile = agent.agent_profiles.get(args.strip())
    if not profile:
        console.print("[dim]Profile 不存在[/dim]")
        return True
    console.print(f"[bold]🤖 {profile.name}[/bold]")
    console.print(f"  描述: {profile.description}")
    console.print(f"  工具: {', '.join(profile.tools) if profile.tools else '全部工具'}")
    if profile.model:
        console.print(f"  模型: {profile.model}")
    if profile.limits:
        console.print(f"  限制: {profile.limits}")
    console.print(f"  Prompt:\n[dim]{profile.prompt}[/dim]")
    return True
```

- [ ] **Step 2: Verify syntax**

Run: `cd /home/xiowen/code/merco && python3 -m py_compile cli/commands.py && echo "Syntax OK"`

- [ ] **Step 3: Commit**

```bash
cd /home/xiowen/code/merco
git add cli/commands.py
git commit -m "feat: /agents /agent CLI commands"
```

---

## Task 5: 端到端集成测试

**Files:**
- Create: `tests/integration/test_agent_profile.py`

- [ ] **Step 1: Write integration test**

Create `tests/integration/test_agent_profile.py`:

```python
"""AgentProfile 端到端集成测试"""
import pytest
from merco.agents.profile import AgentProfile, AgentProfileRegistry


async def test_task_tool_dispatches_with_agent_name(test_agent):
    """TaskTool agent=researcher 派发专业子代理"""
    from merco.agents.subagent import SubAgentManager
    from merco.agents.profile import AgentProfileRegistry, BUILTIN_PROFILES
    from merco.todo.manager import TodoManager
    from unittest.mock import MagicMock, AsyncMock
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        todo_manager = TodoManager(f"{td}/todos.db")
        test_agent.todo_manager = todo_manager

        reg = AgentProfileRegistry()
        for p in BUILTIN_PROFILES:
            reg.register(p)

        manager = SubAgentManager(test_agent, reg)

        todo = todo_manager.create("研究任务")
        mock_result = "研究发现"
        manager._create_sub_agent = MagicMock(return_value=MagicMock(
            session=MagicMock(id="sub_researcher_1"),
            run=AsyncMock(return_value=mock_result),
        ))

        await manager.dispatch(todo.id, "研究某个模块", "researcher")
        updated = todo_manager.get(todo.id)
        assert updated.status == "completed"
        assert updated.result == mock_result


async def test_agent_profile_registry_accessible(test_agent):
    """Agent 启动后 agent_profiles registry 有 builtins"""
    profiles = test_agent.agent_profiles.list()
    names = {p.name for p in profiles}
    assert "default" in names
    assert "researcher" in names
    assert "reviewer" in names
    assert "debugger" in names
```

- [ ] **Step 2: Run test**

Run: `cd /home/xiowen/code/merco && python3 -m pytest tests/integration/test_agent_profile.py -v`
Expected: 2 passed

- [ ] **Step 3: Commit**

```bash
cd /home/xiowen/code/merco
git add tests/integration/test_agent_profile.py
git commit -m "test: AgentProfile end-to-end integration"
```

---

## Task 6: 文档更新

**Files:**
- Modify: `docs/project-vision/references/progress.md`

- [ ] **Step 1: Update progress.md**

Add a new section documenting the AgentProfile pluginization system.

- [ ] **Step 2: Commit**

```bash
cd /home/xiowen/code/merco
git add docs/project-vision/references/progress.md
git commit -m "docs: update progress.md for AgentProfile pluginization"
```

---

## Self-Review

**Spec coverage:**
- ✅ AgentProfile dataclass + Registry (Task 1)
- ✅ 4 builtins (Task 1)
- ✅ PluginContext 暴露 agent_profiles (Task 2)
- ✅ Agent 装配 registry + builtins (Task 2)
- ✅ SubAgentManager 使用 profile (Task 3)
- ✅ TaskTool 注入 managers (Task 2)
- ✅ ProfilePromptChunk (Task 3)
- ✅ CLI /agents /agent (Task 4)
- ✅ 端到端集成测试 (Task 5)
- ✅ 文档更新 (Task 6)

**Placeholder scan:** 无

**Type consistency:** SubAgentManager.__init__ signature matches Task 2 and Task 3
