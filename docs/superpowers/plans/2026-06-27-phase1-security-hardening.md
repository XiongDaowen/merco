# merco Phase 1 安全加固 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 收紧 PluginContext 暴露面、修复插件激活时序、删除重复/废弃代码

**Architecture:** PluginContext 白名单 API + Agent 初始化顺序重排 + 废弃模块删除

**Tech Stack:** Python 3.12, pytest

---

## 文件结构

| 文件 | 变更 |
|------|------|
| `merco/plugins/base.py` | 移除 security_pipeline，add_processor 加白名单 |
| `merco/core/agent.py` | PluginContext 创建时传齐扩展点，移除后置赋值 |
| `merco/sandbox/__init__.py` | 移除 PermissionManager export |
| `merco/memory/compressor.py` | 删除 |
| `merco/sandbox/permissions.py` | 删除 |
| `merco/sandbox/isolation.py` | 删除 |
| `tests/plugins/test_plugin_base.py` | 新增安全测试 |
| `tests/plugins/test_plugin_integration.py` | 新增 activate 时序测试 |

---

## Task 1: PluginContext 安全加固

**Files:**
- Modify: `merco/plugins/base.py`
- Test: `tests/plugins/test_plugin_base.py`

- [ ] **Step 1: Add failing tests**

Append to `tests/plugins/test_plugin_base.py`:

```python

def test_plugin_context_does_not_expose_security_pipeline(ctx):
    """PluginContext 不直接暴露 security_pipeline，避免插件绕过沙箱"""
    assert not hasattr(ctx, "security_pipeline")


def test_add_processor_rejects_non_whitelisted_pipeline(ctx):
    """add_processor 只允许白名单 pipeline"""
    import pytest
    with pytest.raises(ValueError, match="not extensible"):
        ctx.add_processor("security_pipeline", object())


def test_add_processor_allows_context_pipeline(ctx):
    """add_processor 允许白名单内 pipeline"""
    class DummyProcessor:
        name = "dummy"
        async def process(self, messages, **kwargs):
            return messages

    ctx.add_processor("context_pipeline", DummyProcessor())
    assert any(p.name == "dummy" for p in ctx.context_pipeline._processors)
```

If the existing `ctx` fixture does not include `context_pipeline`, update it to add:

```python
from merco.context.pipeline import ContextPipeline
...
context_pipeline=ContextPipeline(),
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/xiowen/code/merco && python3 -m pytest tests/plugins/test_plugin_base.py -v`
Expected: fails because security_pipeline exists / add_processor allows it

- [ ] **Step 3: Harden PluginContext**

In `merco/plugins/base.py`:

1. Remove `security_pipeline` parameter from `PluginContext.__init__`
2. Remove `self.security_pipeline = security_pipeline`
3. Add module-level whitelist:

```python
_PIPELINE_WHITELIST = {
    "result_pipeline",
    "recovery_pipeline",
    "memory_save_pipeline",
    "context_pipeline",
}
```

4. Change `add_processor` to:

```python
    def add_processor(self, pipeline_name: str, processor) -> None:
        """加处理器到白名单管线"""
        if pipeline_name not in _PIPELINE_WHITELIST:
            raise ValueError(f"Pipeline '{pipeline_name}' not extensible")
        pipeline = getattr(self, pipeline_name, None)
        if pipeline and hasattr(pipeline, 'use'):
            pipeline.use(processor)
```

- [ ] **Step 4: Run tests**

Run: `cd /home/xiowen/code/merco && python3 -m pytest tests/plugins/test_plugin_base.py -v`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
cd /home/xiowen/code/merco
git add merco/plugins/base.py tests/plugins/test_plugin_base.py
git commit -m "fix: harden PluginContext pipeline access"
```

---

## Task 2: Agent activate_all 时序修复

**Files:**
- Modify: `merco/core/agent.py`
- Test: `tests/plugins/test_plugin_integration.py`

- [ ] **Step 1: Add failing test**

Append to `tests/plugins/test_plugin_integration.py`:

```python

async def test_plugins_see_all_extension_points_on_activate(test_agent):
    """插件 activate(ctx) 时应能看到所有扩展点"""
    from merco.plugins.base import Plugin

    seen = {}

    class ProbePlugin(Plugin):
        name = "probe"
        version = "1.0.0"
        description = "probe"

        async def activate(self, ctx):
            seen["context_pipeline"] = ctx.context_pipeline is not None
            seen["todo_manager"] = ctx.todo_manager is not None
            seen["sub_agent_manager"] = ctx.sub_agent_manager is not None
            seen["memory_backends"] = ctx.memory_backends is not None
            seen["agent_profiles"] = ctx.agent_profiles is not None
            seen["security_pipeline"] = hasattr(ctx, "security_pipeline")

    test_agent.plugin_manager.register(ProbePlugin())
    await test_agent.plugin_manager.activate("probe")

    assert seen["context_pipeline"] is True
    assert seen["todo_manager"] is True
    assert seen["sub_agent_manager"] is True
    assert seen["memory_backends"] is True
    assert seen["agent_profiles"] is True
    assert seen["security_pipeline"] is False
```

- [ ] **Step 2: Run test**

Run: `cd /home/xiowen/code/merco && python3 -m pytest tests/plugins/test_plugin_integration.py::test_plugins_see_all_extension_points_on_activate -v`
Expected: may fail if ctx missing fields

- [ ] **Step 3: Reorder Agent.__init__**

In `merco/core/agent.py`:

1. Keep `self._security_pipeline` internal and remove `self._plugin_ctx.security_pipeline = ...`
2. Ensure `PluginContext(...)` constructor includes all non-security extension points directly:

```python
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
    todo_manager=self.todo_manager,
    sub_agent_manager=self.sub_agent_manager,
    context_pipeline=self.context_pipeline,
    memory_backends=self.memory_backends,
    agent_profiles=self.agent_profiles,
)
```

3. If any of these are currently created after PluginContext, move their creation before PluginContext.

4. Activate plugins after PluginContext is fully populated.

- [ ] **Step 4: Run tests**

Run: `cd /home/xiowen/code/merco && python3 -m pytest tests/plugins/test_plugin_integration.py tests/plugins/test_plugin_base.py -v`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
cd /home/xiowen/code/merco
git add merco/core/agent.py tests/plugins/test_plugin_integration.py
git commit -m "fix: populate PluginContext before plugin activation"
```

---

## Task 3: 删除重复/废弃代码

**Files:**
- Delete: `merco/memory/compressor.py`
- Delete: `merco/sandbox/permissions.py`
- Delete: `merco/sandbox/isolation.py`
- Modify: `merco/sandbox/__init__.py`

- [ ] **Step 1: Verify references**

Run:

```bash
cd /home/xiowen/code/merco
grep -R "memory.compressor\|ContextCompressor" merco tests --include='*.py'
grep -R "sandbox.permissions\|PermissionManager" merco tests --include='*.py'
grep -R "sandbox.isolation\|SandboxIsolation" merco tests --include='*.py'
```

Expected:
- `ContextCompressor` only in deleted file / docs comments, no runtime import
- `PermissionManager` only in `sandbox/__init__.py` + deleted file
- `SandboxIsolation` only in deleted file

- [ ] **Step 2: Update sandbox/__init__.py**

Remove:

```python
from .permissions import PermissionManager
...
"PermissionManager",
```

- [ ] **Step 3: Delete files**

```bash
rm merco/memory/compressor.py merco/sandbox/permissions.py merco/sandbox/isolation.py
```

- [ ] **Step 4: Run relevant tests**

Run:

```bash
cd /home/xiowen/code/merco
python3 -m pytest tests/context/ tests/memory/ tests/sandbox/ tests/test_guard.py -v
```

Expected: all pass

- [ ] **Step 5: Commit**

```bash
cd /home/xiowen/code/merco
git add merco/memory/compressor.py merco/sandbox/permissions.py merco/sandbox/isolation.py merco/sandbox/__init__.py
git commit -m "refactor: remove deprecated compressor and unused sandbox modules"
```

---

## Task 4: 文档更新

**Files:**
- Modify: `docs/project-vision/references/progress.md`
- Modify: `docs/project-vision/references/architecture-refactor-plan.md`

- [ ] **Step 1: Update progress.md**

Add Phase 1 completion note:

```markdown
- **Phase 1 安全加固（架构重构）**:
  - PluginContext 移除 `security_pipeline` 直接暴露，防止插件绕过沙箱
  - `add_processor()` 改为白名单模式
  - Agent 插件激活时序修复：PluginContext 激活前完整注入扩展点
  - 删除重复/废弃模块：`memory/compressor.py`、`sandbox/permissions.py`、`sandbox/isolation.py`
```

- [ ] **Step 2: Update architecture-refactor-plan.md**

Mark Phase 1 items as done:

```markdown
### Phase 1 — 安全加固（已完成）
```

- [ ] **Step 3: Commit**

```bash
cd /home/xiowen/code/merco
git add docs/project-vision/references/progress.md docs/project-vision/references/architecture-refactor-plan.md
git commit -m "docs: mark Phase 1 security hardening complete"
```

---

## Self-Review

**Spec coverage:**
- ✅ PluginContext 移除 security_pipeline (Task 1)
- ✅ add_processor 白名单 (Task 1)
- ✅ activate_all 时序修复 (Task 2)
- ✅ 删除重复/废弃代码 (Task 3)
- ✅ 测试 (Tasks 1-3)
- ✅ 文档 (Task 4)

**Placeholder scan:** 无

**Risk:** 删除文件只在确认无 runtime import 后进行
