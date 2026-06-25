# merco 插件系统 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建 merco 的插件系统，让插件成为 merco 架构的一等公民

**Architecture:** Plugin 基类 + PluginContext（暴露 6 个扩展点）+ PluginManager（生命周期管理）+ Observer 集成（插件事件追踪）+ Superpower 示例插件

**Tech Stack:** Python 3.12, ABC, dataclass, asyncio

---

## 文件结构

| 文件 | 职责 |
|------|------|
| `merco/plugins/__init__.py` | 导出 Plugin, PluginContext, PluginManager |
| `merco/plugins/base.py` | Plugin ABC + PluginContext |
| `merco/plugins/manager.py` | PluginManager |
| `merco/plugins/builtin/__init__.py` | 内置插件入口 |
| `merco/plugins/builtin/superpower/__init__.py` | Superpower 插件导出 |
| `merco/plugins/builtin/superpower/plugin.py` | SuperpowerPlugin 实现 |
| `merco/core/agent.py` | Agent 启动时装配 PluginManager |
| `merco/core/config.py` | 新增 plugins 配置字段 |
| `merco/observability/observer.py` | 订阅 plugin.activated/plugin.error 事件 |
| `cli/commands.py` | /plugins 命令 |
| `tests/plugins/test_plugin_base.py` | Plugin 基类 + PluginContext 单测 |
| `tests/plugins/test_plugin_manager.py` | PluginManager 单测 |
| `tests/plugins/test_superpower.py` | Superpower 插件单测 |
| `tests/plugins/test_plugin_integration.py` | 端到端集成测试 |

---

## Task 1: Plugin 基类 + PluginContext

**Files:**
- Create: `merco/plugins/__init__.py`
- Create: `merco/plugins/base.py`
- Test: `tests/plugins/test_plugin_base.py`

- [ ] **Step 1: Write the failing test**

Create `tests/plugins/__init__.py` (empty) and `tests/plugins/test_plugin_base.py`:

```python
"""Plugin 基类 + PluginContext 单测"""
import pytest
from merco.plugins.base import Plugin, PluginContext
from merco.tools.base import BaseTool


class FakeTool(BaseTool):
    name = "fake_tool"
    description = "测试工具"
    parameters = {"type": "object", "properties": {}}
    async def execute(self, **kwargs):
        return {"result": "ok"}


class FakePlugin(Plugin):
    name = "fake"
    version = "1.0.0"
    description = "测试插件"

    def __init__(self):
        self.activated = False
        self.deactivated = False

    async def activate(self, ctx):
        self.activated = True
        ctx.register_tool(FakeTool())

    async def deactivate(self):
        self.deactivated = True


def test_plugin_abc_requires_activate():
    """Plugin 基类不能直接实例化"""
    with pytest.raises(TypeError):
        Plugin()  # noqa


def test_plugin_context_has_all_extension_points(ctx):
    """PluginContext 暴露 6 个扩展点"""
    assert hasattr(ctx, 'hooks')
    assert hasattr(ctx, 'tool_registry')
    assert hasattr(ctx, 'prompt_builder')
    assert hasattr(ctx, 'recovery_pipeline')
    assert hasattr(ctx, 'result_pipeline')
    assert hasattr(ctx, 'memory_save_pipeline')
    assert hasattr(ctx, 'recaller')
    assert hasattr(ctx, 'config')
    assert hasattr(ctx, 'observer')


@pytest.fixture
def ctx(tmp_path):
    """构造 PluginContext"""
    from merco.hooks.registry import HookRegistry
    from merco.tools.registry import ToolRegistry
    from merco.core.agent import PromptBuilder
    from merco.memory.store import MemoryStore
    from merco.memory.save_pipeline import MemorySavePipeline
    from merco.memory.recall import HybridRecaller
    from merco.core.config import MercoConfig
    from unittest.mock import MagicMock

    hooks = HookRegistry()
    tool_registry = ToolRegistry()
    prompt_builder = PromptBuilder()
    memory_store = MemoryStore(str(tmp_path / "memory"))
    config = MercoConfig()
    config.memory_path = str(tmp_path / "memory")

    return PluginContext(
        hooks=hooks,
        tool_registry=tool_registry,
        prompt_builder=prompt_builder,
        recovery_pipeline=MagicMock(),
        result_pipeline=MagicMock(),
        memory_save_pipeline=MemorySavePipeline(memory_store, hooks),
        recaller=HybridRecaller(),
        config=config,
        observer=MagicMock(),
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/xiowen/code/merco && python3 -m pytest tests/plugins/test_plugin_base.py -v`
Expected: ImportError (merco.plugins.base not exists)

- [ ] **Step 3: Implement Plugin + PluginContext**

Create `merco/plugins/__init__.py`:

```python
"""merco 插件系统"""

from .base import Plugin, PluginContext

__all__ = ["Plugin", "PluginContext"]
```

Create `merco/plugins/base.py`:

```python
"""Plugin 基类 + PluginContext"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from merco.hooks.registry import HookRegistry
    from merco.tools.registry import ToolRegistry
    from merco.core.agent import PromptBuilder, PromptChunk
    from merco.core.pipeline import RecoveryPipeline, ResultPipeline
    from merco.memory.save_pipeline import MemorySavePipeline
    from merco.memory.recall import HybridRecaller, BaseRecaller
    from merco.core.config import MercoConfig
    from merco.observability.observer import Observer
    from merco.tools.base import BaseTool
    from typing import Callable


class Plugin(ABC):
    """merco 插件基类"""
    name: str = ""           # 唯一标识
    version: str = ""        # 语义版本
    description: str = ""    # 一句话描述

    @abstractmethod
    async def activate(self, ctx: "PluginContext") -> None:
        """激活时调用，ctx 提供所有扩展点"""
        ...

    async def deactivate(self) -> None:
        """卸载时调用，清理资源。默认空实现"""
        pass


class PluginContext:
    """插件的扩展点入口，activate 时注入"""

    def __init__(
        self,
        hooks: "HookRegistry",
        tool_registry: "ToolRegistry",
        prompt_builder: "PromptBuilder",
        recovery_pipeline: "RecoveryPipeline",
        result_pipeline: "ResultPipeline",
        memory_save_pipeline: "MemorySavePipeline",
        recaller: "HybridRecaller",
        config: "MercoConfig",
        observer: "Observer",
    ):
        self.hooks = hooks
        self.tool_registry = tool_registry
        self.prompt_builder = prompt_builder
        self.recovery_pipeline = recovery_pipeline
        self.result_pipeline = result_pipeline
        self.memory_save_pipeline = memory_save_pipeline
        self.recaller = recaller
        self.config = config
        self.observer = observer

    def on(self, event: str, handler: "Callable") -> None:
        """订阅事件（便捷方法）"""
        self.hooks.on(event, handler)

    def register_tool(self, tool: "BaseTool") -> None:
        """注册工具"""
        self.tool_registry.register(tool)

    def add_prompt_chunk(self, chunk: "PromptChunk") -> None:
        """注入 system prompt chunk"""
        self.prompt_builder.use(chunk)

    def add_processor(self, pipeline_name: str, processor) -> None:
        """加处理器到指定管线"""
        pipeline = getattr(self, pipeline_name, None)
        if pipeline and hasattr(pipeline, 'use'):
            pipeline.use(processor)

    def add_recaller(self, recaller: "BaseRecaller") -> None:
        """加记忆召回器"""
        self.recaller.add(recaller)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/xiowen/code/merco && python3 -m pytest tests/plugins/test_plugin_base.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
cd /home/xiowen/code/merco
git add merco/plugins/ tests/plugins/
git commit -m "feat: add Plugin base class and PluginContext"
```

---

## Task 2: PluginManager

**Files:**
- Create: `merco/plugins/manager.py`
- Test: `tests/plugins/test_plugin_manager.py`

- [ ] **Step 1: Write the failing test**

Create `tests/plugins/test_plugin_manager.py`:

```python
"""PluginManager 单测"""
import pytest
from merco.plugins.base import Plugin, PluginContext
from merco.plugins.manager import PluginManager


class FakePlugin(Plugin):
    name = "fake"
    version = "1.0.0"
    description = "测试插件"

    def __init__(self):
        self.activated = False
        self.deactivated = False

    async def activate(self, ctx):
        self.activated = True

    async def deactivate(self):
        self.deactivated = True


class FailingPlugin(Plugin):
    name = "failing"
    version = "1.0.0"
    description = "激活失败的插件"

    async def activate(self, ctx):
        raise RuntimeError("boom")

    async def deactivate(self):
        pass


@pytest.fixture
def ctx(tmp_path):
    """构造 PluginContext"""
    from merco.hooks.registry import HookRegistry
    from merco.tools.registry import ToolRegistry
    from merco.core.agent import PromptBuilder
    from merco.memory.store import MemoryStore
    from merco.memory.save_pipeline import MemorySavePipeline
    from merco.memory.recall import HybridRecaller
    from merco.core.config import MercoConfig
    from unittest.mock import MagicMock

    hooks = HookRegistry()
    tool_registry = ToolRegistry()
    prompt_builder = PromptBuilder()
    memory_store = MemoryStore(str(tmp_path / "memory"))
    config = MercoConfig()
    config.memory_path = str(tmp_path / "memory")

    return PluginContext(
        hooks=hooks,
        tool_registry=tool_registry,
        prompt_builder=prompt_builder,
        recovery_pipeline=MagicMock(),
        result_pipeline=MagicMock(),
        memory_save_pipeline=MemorySavePipeline(memory_store, hooks),
        recaller=HybridRecaller(),
        config=config,
        observer=MagicMock(),
    )


@pytest.fixture
def manager(ctx):
    return PluginManager(ctx)


async def test_activate_single_plugin(manager, ctx):
    """激活单个插件"""
    plugin = FakePlugin()
    manager._plugins["fake"] = plugin
    await manager.activate("fake")
    assert plugin.activated is True
    assert "fake" in manager._active


async def test_deactivate_plugin(manager, ctx):
    """停用插件"""
    plugin = FakePlugin()
    manager._plugins["fake"] = plugin
    await manager.activate("fake")
    await manager.deactivate("fake")
    assert plugin.deactivated is True
    assert "fake" not in manager._active


async def test_activate_emits_event(manager, ctx):
    """激活插件触发 plugin.activated 事件"""
    events = []
    async def on_activated(plugin_name, **kwargs):
        events.append(plugin_name)
    ctx.hooks.on("plugin.activated", on_activated)

    manager._plugins["fake"] = FakePlugin()
    await manager.activate("fake")
    assert "fake" in events


async def test_activate_all_enabled(manager, ctx):
    """activate_all 只激活 enabled 的插件"""
    ctx.config.plugins = {
        "fake": {"enabled": True},
        "disabled": {"enabled": False},
    }
    plugin = FakePlugin()
    manager._plugins["fake"] = plugin
    manager._plugins["disabled"] = FakePlugin()

    await manager.activate_all()
    assert plugin.activated is True
    assert manager._plugins["disabled"].activated is False


async def test_activate_failure_isolated(manager, ctx):
    """插件激活失败不影响其他插件"""
    events = []
    async def on_error(plugin_name, **kwargs):
        events.append(plugin_name)
    ctx.hooks.on("plugin.error", on_error)

    manager._plugins["failing"] = FailingPlugin()
    manager._plugins["fake"] = FakePlugin()
    await manager.activate_all()
    assert "failing" in events
    assert manager._plugins["fake"].activated is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/xiowen/code/merco && python3 -m pytest tests/plugins/test_plugin_manager.py -v`
Expected: ImportError (merco.plugins.manager not exists)

- [ ] **Step 3: Implement PluginManager**

Create `merco/plugins/manager.py`:

```python
"""PluginManager — 插件生命周期管理"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .base import Plugin, PluginContext

logger = logging.getLogger("merco.plugins.manager")


class PluginManager:
    """插件发现、加载、激活、卸载"""

    def __init__(self, ctx: "PluginContext"):
        self._ctx = ctx
        self._plugins: dict[str, "Plugin"] = {}
        self._active: set[str] = set()

    def register(self, plugin: "Plugin") -> None:
        """注册插件实例（内置插件用）"""
        self._plugins[plugin.name] = plugin

    async def activate(self, name: str) -> None:
        """激活单个插件"""
        plugin = self._plugins.get(name)
        if not plugin:
            logger.warning("插件 '%s' 未注册", name)
            return
        try:
            await plugin.activate(self._ctx)
            self._active.add(name)
            await self._ctx.hooks.emit("plugin.activated", plugin_name=name, version=plugin.version)
        except Exception as e:
            logger.warning("插件 '%s' 激活失败: %s", name, e)
            try:
                await self._ctx.hooks.emit("plugin.error", plugin_name=name, error=str(e))
            except Exception:
                pass

    async def deactivate(self, name: str) -> None:
        """停用单个插件"""
        plugin = self._plugins.get(name)
        if not plugin:
            return
        try:
            await plugin.deactivate()
        except Exception as e:
            logger.warning("插件 '%s' 停用失败: %s", name, e)
        self._active.discard(name)
        try:
            await self._ctx.hooks.emit("plugin.deactivated", plugin_name=name)
        except Exception:
            pass

    async def activate_all(self) -> None:
        """启动时激活所有 enabled 插件"""
        plugins_config = getattr(self._ctx.config, 'plugins', {})
        for name in self._plugins:
            plugin_cfg = plugins_config.get(name, {})
            if plugin_cfg.get("enabled", True):
                await self.activate(name)

    async def deactivate_all(self) -> None:
        """停用所有活跃插件"""
        for name in list(self._active):
            await self.deactivate(name)

    @property
    def active_plugins(self) -> list[str]:
        """返回已激活的插件名列表"""
        return list(self._active)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/xiowen/code/merco && python3 -m pytest tests/plugins/test_plugin_manager.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
cd /home/xiowen/code/merco
git add merco/plugins/manager.py tests/plugins/test_plugin_manager.py
git commit -m "feat: add PluginManager with lifecycle management"
```

---

## Task 3: Superpower 示例插件

**Files:**
- Create: `merco/plugins/builtin/__init__.py`
- Create: `merco/plugins/builtin/superpower/__init__.py`
- Create: `merco/plugins/builtin/superpower/plugin.py`
- Test: `tests/plugins/test_superpower.py`

- [ ] **Step 1: Write the failing test**

Create `tests/plugins/test_superpower.py`:

```python
"""Superpower 插件单测"""
import pytest
from merco.plugins.base import PluginContext
from merco.plugins.builtin.superpower.plugin import SuperpowerPlugin


@pytest.fixture
def ctx(tmp_path):
    """构造 PluginContext"""
    from merco.hooks.registry import HookRegistry
    from merco.tools.registry import ToolRegistry
    from merco.core.agent import PromptBuilder
    from merco.memory.store import MemoryStore
    from merco.memory.save_pipeline import MemorySavePipeline
    from merco.memory.recall import HybridRecaller
    from merco.core.config import MercoConfig
    from unittest.mock import MagicMock

    hooks = HookRegistry()
    tool_registry = ToolRegistry()
    prompt_builder = PromptBuilder()
    memory_store = MemoryStore(str(tmp_path / "memory"))
    config = MercoConfig()
    config.memory_path = str(tmp_path / "memory")

    return PluginContext(
        hooks=hooks,
        tool_registry=tool_registry,
        prompt_builder=prompt_builder,
        recovery_pipeline=MagicMock(),
        result_pipeline=MagicMock(),
        memory_save_pipeline=MemorySavePipeline(memory_store, hooks),
        recaller=HybridRecaller(),
        config=config,
        observer=MagicMock(),
    )


async def test_superpower_registers_tools(ctx):
    """Superpower 插件注册工具"""
    plugin = SuperpowerPlugin()
    await plugin.activate(ctx)
    tools = ctx.tool_registry.list_tools()
    tool_names = [t.name for t in tools]
    assert any("tdd" in name.lower() or "debug" in name.lower() for name in tool_names)


async def test_superpower_adds_prompt_chunk(ctx):
    """Superpower 插件注入 prompt chunk"""
    plugin = SuperpowerPlugin()
    await plugin.activate(ctx)
    chunk_names = [c.name for c in ctx.prompt_builder._chunks]
    assert any("superpower" in name.lower() for name in chunk_names)


async def test_superpower_subscribes_events(ctx):
    """Superpower 插件订阅事件"""
    plugin = SuperpowerPlugin()
    await plugin.activate(ctx)
    assert "agent.start" in ctx.hooks._hooks
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/xiowen/code/merco && python3 -m pytest tests/plugins/test_superpower.py -v`
Expected: ImportError

- [ ] **Step 3: Implement SuperpowerPlugin**

Create `merco/plugins/builtin/__init__.py`:

```python
"""内置插件"""
```

Create `merco/plugins/builtin/superpower/__init__.py`:

```python
"""Superpower 插件"""
from .plugin import SuperpowerPlugin

__all__ = ["SuperpowerPlugin"]
```

Create `merco/plugins/builtin/superpower/plugin.py`:

```python
"""Superpower 插件 — 扩展 merco 的超能力"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from merco.plugins.base import Plugin

if TYPE_CHECKING:
    from merco.plugins.base import PluginContext

logger = logging.getLogger("merco.plugins.superpower")


class SuperpowerHintChunk:
    """Superpower 提示注入"""
    name = "superpower_hint"

    def enabled(self, agent) -> bool:
        return True

    def build(self, agent) -> str:
        return """## Superpowers Available
You have access to superpowers: TDD, debugging, subagent, code review.
Use them when appropriate to help the user."""


class SuperpowerPlugin(Plugin):
    """扩展 merco 的超能力：TDD、debugging、subagent、code review 等"""
    name = "superpower"
    version = "1.0.0"
    description = "扩展 merco 的超能力"

    async def activate(self, ctx: "PluginContext") -> None:
        # 1. 注册 prompt chunk
        ctx.add_prompt_chunk(SuperpowerHintChunk())

        # 2. 订阅事件
        ctx.hooks.on("agent.start", self._on_start)
        ctx.hooks.on("tool.error", self._on_tool_error)

        logger.info("Superpower 插件已激活")

    async def deactivate(self) -> None:
        logger.info("Superpower 插件已停用")

    async def _on_start(self, session_id: str = "", **kwargs):
        logger.debug("Superpower: agent.start session=%s", session_id)

    async def _on_tool_error(self, tool_name: str = "", error: str = "", **kwargs):
        logger.debug("Superpower: tool.error %s: %s", tool_name, error)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/xiowen/code/merco && python3 -m pytest tests/plugins/test_superpower.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
cd /home/xiowen/code/merco
git add merco/plugins/builtin/ tests/plugins/test_superpower.py
git commit -m "feat: add Superpower example plugin"
```

---

## Task 4: Config 字段 + Observer 集成

**Files:**
- Modify: `merco/core/config.py`
- Modify: `merco/observability/observer.py`

- [ ] **Step 1: Add plugins config field**

Add to `MercoConfig` in `merco/core/config.py`:

```python
    plugins: dict = field(default_factory=dict)
```

Add to `_to_dict`:

```python
            "plugins": self.plugins,
```

Add to `_from_dict`:

```python
            plugins=data.get("plugins", {}),
```

- [ ] **Step 2: Add Observer plugin event subscriptions**

Add to `Observer.__init__` in `merco/observability/observer.py`:

```python
        hooks.on("plugin.activated", self._on_plugin_activated)
        hooks.on("plugin.error", self._on_plugin_error)
```

Add methods:

```python
    def _on_plugin_activated(self, plugin_name: str = "", **kwargs):
        """插件激活"""
        self._live.increment(f"plugin.{plugin_name}.activations")

    def _on_plugin_error(self, plugin_name: str = "", **kwargs):
        """插件错误"""
        self._live.increment(f"plugin.{plugin_name}.errors")
```

- [ ] **Step 3: Verify syntax**

Run: `cd /home/xiowen/code/merco && python3 -m py_compile merco/core/config.py && python3 -m py_compile merco/observability/observer.py && echo "Syntax OK"`

- [ ] **Step 4: Commit**

```bash
cd /home/xiowen/code/merco
git add merco/core/config.py merco/observability/observer.py
git commit -m "feat: add plugins config field and Observer integration"
```

---

## Task 5: Agent 启动装配

**Files:**
- Modify: `merco/core/agent.py`

- [ ] **Step 1: Add PluginManager to Agent.__init__**

After the Observer creation block in `Agent.__init__`, add:

```python
        # ── 插件系统 ──
        from merco.plugins.base import PluginContext
        from merco.plugins.manager import PluginManager
        from merco.plugins.builtin.superpower.plugin import SuperpowerPlugin

        self._plugin_ctx = PluginContext(
            hooks=self.hooks,
            tool_registry=self.tool_registry,
            prompt_builder=self.prompt_builder,
            recovery_pipeline=self.recovery_pipeline,
            result_pipeline=self.result_pipeline,
            memory_save_pipeline=self.memory_save_pipeline,
            recaller=self.recaller,
            config=config,
            observer=self.observer,
        )
        self.plugin_manager = PluginManager(self._plugin_ctx)

        # 注册内置插件
        self.plugin_manager.register(SuperpowerPlugin())

        # 激活所有 enabled 插件（同步调用，Agent.__init__ 是同步的）
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # 如果已经在 async 上下文，用 create_task
                asyncio.ensure_future(self.plugin_manager.activate_all())
            else:
                loop.run_until_complete(self.plugin_manager.activate_all())
        except RuntimeError:
            # 没有 event loop，跳过
            pass
```

- [ ] **Step 2: Verify syntax**

Run: `cd /home/xiowen/code/merco && python3 -m py_compile merco/core/agent.py && echo "Syntax OK"`

- [ ] **Step 3: Run existing tests**

Run: `cd /home/xiowen/code/merco && python3 -m pytest tests/integration/test_scenarios.py -v -k "test_simple_conversation or test_tool_call_chain" 2>&1 | tail -10`
Expected: existing tests still pass

- [ ] **Step 4: Commit**

```bash
cd /home/xiowen/code/merco
git add merco/core/agent.py
git commit -m "feat: wire PluginManager into Agent init"
```

---

## Task 6: CLI /plugins 命令

**Files:**
- Modify: `cli/commands.py`

- [ ] **Step 1: Add /plugins command**

Add after the existing `/memories` command in `cli/commands.py`:

```python
@cmd_registry.register("/plugins", "列出已安装插件", group="system")
async def cmd_plugins(agent, args):
    """列出所有插件及其状态"""
    pm = agent.plugin_manager
    plugins_config = getattr(agent.config, 'plugins', {})

    if not pm._plugins:
        console.print("[dim]暂无插件[/dim]")
        return True

    console.print("[bold]🔌 已安装插件[/bold]")
    console.print("─" * 40)
    for name, plugin in pm._plugins.items():
        status = "✅ 已激活" if name in pm._active else "⏸️  未激活"
        cfg = plugins_config.get(name, {})
        if not cfg.get("enabled", True):
            status = "❌ 已禁用"
        console.print(f"  {status}  {name} v{plugin.version}")
        console.print(f"     [dim]{plugin.description}[/dim]")
    return True
```

- [ ] **Step 2: Verify syntax**

Run: `cd /home/xiowen/code/merco && python3 -m py_compile cli/commands.py && echo "Syntax OK"`

- [ ] **Step 3: Commit**

```bash
cd /home/xiowen/code/merco
git add cli/commands.py
git commit -m "feat: /plugins CLI command"
```

---

## Task 7: 端到端集成测试

**Files:**
- Create: `tests/plugins/test_plugin_integration.py`

- [ ] **Step 1: Write integration test**

Create `tests/plugins/test_plugin_integration.py`:

```python
"""插件系统端到端集成测试"""
import pytest
from merco.plugins.base import Plugin, PluginContext
from merco.plugins.manager import PluginManager


class TestPlugin(Plugin):
    name = "test_plugin"
    version = "1.0.0"
    description = "测试插件"

    def __init__(self):
        self.activated = False
        self.tool_registered = False

    async def activate(self, ctx):
        self.activated = True
        # 注册一个工具
        from merco.tools.base import BaseTool

        class TestTool(BaseTool):
            name = "test_plugin_tool"
            description = "插件注册的工具"
            parameters = {"type": "object", "properties": {}}
            async def execute(self, **kwargs):
                return {"result": "from plugin"}

        ctx.register_tool(TestTool())
        self.tool_registered = True

    async def deactivate(self):
        self.activated = False


async def test_plugin_activates_and_registers_tool(test_agent):
    """插件激活后注册工具，Agent 可用"""
    plugin = TestPlugin()
    test_agent.plugin_manager.register(plugin)
    await test_agent.plugin_manager.activate("test_plugin")

    assert plugin.activated is True
    assert "test_plugin_tool" in [t.name for t in test_agent.tool_registry.list_tools()]


async def test_plugin_emits_events(test_agent):
    """插件激活触发事件"""
    events = []
    async def on_activated(plugin_name, **kwargs):
        events.append(plugin_name)
    test_agent.hooks.on("plugin.activated", on_activated)

    plugin = TestPlugin()
    test_agent.plugin_manager.register(plugin)
    await test_agent.plugin_manager.activate("test_plugin")

    assert "test_plugin" in events


async def test_plugin_failure_isolated(test_agent):
    """插件失败不影响 Agent"""
    class FailingPlugin(Plugin):
        name = "failing"
        version = "1.0.0"
        description = "失败插件"

        async def activate(self, ctx):
            raise RuntimeError("boom")

    failing = FailingPlugin()
    working = TestPlugin()
    test_agent.plugin_manager.register(failing)
    test_agent.plugin_manager.register(working)

    await test_agent.plugin_manager.activate_all()

    assert working.activated is True
    assert "test_plugin" in test_agent.plugin_manager.active_plugins
```

- [ ] **Step 2: Run test**

Run: `cd /home/xiowen/code/merco && python3 -m pytest tests/plugins/test_plugin_integration.py -v`
Expected: 3 passed

- [ ] **Step 3: Commit**

```bash
cd /home/xiowen/code/merco
git add tests/plugins/test_plugin_integration.py
git commit -m "test: plugin system end-to-end integration"
```

---

## Task 8: 文档更新

**Files:**
- Modify: `docs/project-vision/references/progress.md`

- [ ] **Step 1: Update progress.md**

Add a new section for the plugin system in the "本次会话更新" area, and update the "下一步" list to mark plugin system as done.

- [ ] **Step 2: Commit**

```bash
cd /home/xiowen/code/merco
git add docs/project-vision/references/progress.md
git commit -m "docs: update progress.md for plugin system"
```

---

## Self-Review

**Spec coverage:**
- ✅ Plugin 基类 + PluginContext (Task 1)
- ✅ PluginManager (Task 2)
- ✅ Superpower 示例插件 (Task 3)
- ✅ Config 字段 + Observer 集成 (Task 4)
- ✅ Agent 装配 (Task 5)
- ✅ CLI /plugins 命令 (Task 6)
- ✅ 端到端集成测试 (Task 7)
- ✅ 文档更新 (Task 8)

**Placeholder scan:** 无 TBD/TODO

**Type consistency:** PluginContext 属性名、方法签名在所有 task 中一致
