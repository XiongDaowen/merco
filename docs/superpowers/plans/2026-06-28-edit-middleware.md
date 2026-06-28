# merco EditFile Middleware 解耦 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 EditFile 只负责 SEARCH/REPLACE 规划，confirm/snapshot/write 由 ToolMiddleware 处理

**Architecture:** EditFile 返回 planned_edit，EditApplyMiddleware 在 after 阶段消费 planned_edit 并执行确认、快照、写入

**Tech Stack:** Python 3.12, ToolMiddleware, pytest, Rich diff/confirm existing UI

---

## 文件结构

| 文件 | 职责 |
|------|------|
| `merco/tools/edit.py` | 只负责 SEARCH/REPLACE 规划，返回 planned_edit |
| `merco/tools/middleware.py` | 新增 EditApplyMiddleware |
| `merco/core/agent.py` | Agent 装配 EditApplyMiddleware |
| `tests/tools/test_edit_middleware.py` | EditFile + EditApplyMiddleware 单测 |

---

## Task 1: EditFile 改为 planner

**Files:**
- Modify: `merco/tools/edit.py`
- Test: `tests/tools/test_edit_middleware.py`

- [ ] **Step 1: Write failing tests**

Create `tests/tools/test_edit_middleware.py`:

```python
"""EditFile planner + EditApplyMiddleware 单测"""
import pytest
from merco.tools.edit import EditFile


@pytest.mark.asyncio
async def test_edit_file_returns_planned_edit(tmp_path):
    """EditFile 不写文件，只返回 planned_edit"""
    p = tmp_path / "a.txt"
    p.write_text("hello world", encoding="utf-8")

    tool = EditFile()
    result = await tool.execute(str(p), "hello", "hi")

    assert result["planned_edit"] is True
    assert result["path"] == str(p)
    assert result["old_content"] == "hello world"
    assert result["new_content"] == "hi world"
    assert "diff" in result
    # 文件还没被写入
    assert p.read_text(encoding="utf-8") == "hello world"


@pytest.mark.asyncio
async def test_edit_file_no_change_returns_success(tmp_path):
    """无变化时仍直接返回 success，不需要 middleware"""
    p = tmp_path / "a.txt"
    p.write_text("hello", encoding="utf-8")
    tool = EditFile()
    result = await tool.execute(str(p), "hello", "hello")
    assert result["success"] is True
    assert result["diff"] == ""


@pytest.mark.asyncio
async def test_edit_file_search_missing_error(tmp_path):
    """search 不存在时返回 error"""
    p = tmp_path / "a.txt"
    p.write_text("hello", encoding="utf-8")
    tool = EditFile()
    result = await tool.execute(str(p), "missing", "x")
    assert "error" in result
```

- [ ] **Step 2: Run tests to verify fail**

Run: `cd /home/xiowen/code/merco && python3 -m pytest tests/tools/test_edit_middleware.py -v`
Expected: first test fails because file is written and no planned_edit

- [ ] **Step 3: Modify edit.py**

In `merco/tools/edit.py`:

1. Remove imports:

```python
from merco.sandbox.confirm import confirm_edit
from merco.sandbox import snapshot
```

2. Remove `_get_diff_view()` if unused after change.

3. Replace approval/write section:

```python
        # 原逻辑：confirm_edit + snapshot.track + write_text
```

with:

```python
        return {
            "planned_edit": True,
            "path": path,
            "old_content": old_content,
            "new_content": new_content,
            "diff": diff_text,
        }
```

Keep file existence, search validation, new_content generation, diff generation, and no-change success logic unchanged.

- [ ] **Step 4: Run tests**

Run: `cd /home/xiowen/code/merco && python3 -m pytest tests/tools/test_edit_middleware.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
cd /home/xiowen/code/merco
git add merco/tools/edit.py tests/tools/test_edit_middleware.py
git commit -m "refactor: EditFile returns planned_edit without sandbox dependencies"
```

---

## Task 2: EditApplyMiddleware

**Files:**
- Modify: `merco/tools/middleware.py`
- Test: `tests/tools/test_edit_middleware.py`

- [ ] **Step 1: Append tests**

Append to `tests/tools/test_edit_middleware.py`:

```python
from merco.tools.middleware import EditApplyMiddleware, ToolContext


@pytest.mark.asyncio
async def test_edit_apply_middleware_writes_when_approved(tmp_path, monkeypatch):
    """确认后写文件"""
    p = tmp_path / "a.txt"
    p.write_text("hello world", encoding="utf-8")

    async def approve(*args, **kwargs):
        return True

    tracked = []
    monkeypatch.setattr("merco.tools.middleware.confirm_edit", approve)
    monkeypatch.setattr("merco.tools.middleware.snapshot.track", lambda path, old: tracked.append((path, old)))

    tool = EditFile()
    planned = await tool.execute(str(p), "hello", "hi")
    ctx = ToolContext(tool_name="edit_file", arguments={}, result=planned)

    mw = EditApplyMiddleware(diff_view="unified")
    result = await mw.after(ctx)

    assert result["success"] is True
    assert p.read_text(encoding="utf-8") == "hi world"
    assert tracked == [(str(p), "hello world")]


@pytest.mark.asyncio
async def test_edit_apply_middleware_cancel_does_not_write(tmp_path, monkeypatch):
    """取消后不写文件"""
    p = tmp_path / "a.txt"
    p.write_text("hello world", encoding="utf-8")

    async def reject(*args, **kwargs):
        return False

    monkeypatch.setattr("merco.tools.middleware.confirm_edit", reject)
    monkeypatch.setattr("merco.tools.middleware.snapshot.track", lambda path, old: (_ for _ in ()).throw(AssertionError("should not track")))

    tool = EditFile()
    planned = await tool.execute(str(p), "hello", "hi")
    ctx = ToolContext(tool_name="edit_file", arguments={}, result=planned)

    mw = EditApplyMiddleware(diff_view="unified")
    result = await mw.after(ctx)

    assert result["success"] is False
    assert "取消" in result["message"]
    assert p.read_text(encoding="utf-8") == "hello world"


@pytest.mark.asyncio
async def test_edit_apply_middleware_ignores_non_planned_result():
    """非 planned_edit 结果不处理"""
    mw = EditApplyMiddleware()
    ctx = ToolContext(tool_name="bash", arguments={}, result={"ok": True})
    assert await mw.after(ctx) is None
```

- [ ] **Step 2: Run tests to verify fail**

Run: `cd /home/xiowen/code/merco && python3 -m pytest tests/tools/test_edit_middleware.py -v`
Expected: ImportError EditApplyMiddleware

- [ ] **Step 3: Implement EditApplyMiddleware**

In `merco/tools/middleware.py`:

1. Add imports at top:

```python
from pathlib import Path
from merco.sandbox.confirm import confirm_edit
from merco.sandbox import snapshot
```

2. Append class:

```python
class EditApplyMiddleware(ToolMiddleware):
    """应用 EditFile planned_edit：确认、快照、写入"""
    name = "edit_apply"

    def __init__(self, diff_view: str = "unified"):
        self.diff_view = diff_view

    async def before(self, ctx: ToolContext):
        return None

    async def after(self, ctx: ToolContext):
        result = ctx.result or {}
        if not isinstance(result, dict) or not result.get("planned_edit"):
            return None

        path = result["path"]
        old_content = result["old_content"]
        new_content = result["new_content"]
        diff = result["diff"]

        approved = await confirm_edit(diff, path, 1, old_content, new_content, self.diff_view)
        if not approved:
            return {
                "success": False,
                "path": path,
                "message": "用户已取消修改",
                "diff": diff,
            }

        snapshot.track(path, old_content)
        Path(path).write_text(new_content, encoding="utf-8")
        return {
            "success": True,
            "path": path,
            "diff": diff,
            "message": f"已修改 `{path}`",
        }

    async def on_error(self, ctx: ToolContext):
        return None
```

- [ ] **Step 4: Run tests**

Run: `cd /home/xiowen/code/merco && python3 -m pytest tests/tools/test_edit_middleware.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
cd /home/xiowen/code/merco
git add merco/tools/middleware.py tests/tools/test_edit_middleware.py
git commit -m "feat: add EditApplyMiddleware for confirm snapshot write"
```

---

## Task 3: Agent 装配 EditApplyMiddleware

**Files:**
- Modify: `merco/core/agent.py`

- [ ] **Step 1: Add middleware in Agent.__init__**

Find existing middleware wiring:

```python
from merco.tools.middleware import GuardMiddleware, ErrorHandlingMiddleware
self.tool_registry.use(GuardMiddleware(self.guard))
self.tool_registry.use(ErrorHandlingMiddleware())
```

Change to:

```python
from merco.tools.middleware import GuardMiddleware, EditApplyMiddleware, ErrorHandlingMiddleware
self.tool_registry.use(GuardMiddleware(self.guard))
self.tool_registry.use(EditApplyMiddleware(diff_view=config.diff_view))
self.tool_registry.use(ErrorHandlingMiddleware())
```

- [ ] **Step 2: Run behavior tests**

Run:

```bash
cd /home/xiowen/code/merco
python3 -m pytest tests/tools/test_edit_middleware.py tests/integration/test_tool_middleware.py -v
```

- [ ] **Step 3: Commit**

```bash
cd /home/xiowen/code/merco
git add merco/core/agent.py
git commit -m "feat: wire EditApplyMiddleware into Agent tool chain"
```

---

## Task 4: 验证 edit.py 不再依赖 sandbox + 文档更新

**Files:**
- Modify: `docs/project-vision/references/architecture-refactor-plan.md`
- Modify: `docs/project-vision/references/progress.md`

- [ ] **Step 1: Verify imports**

Run:

```bash
cd /home/xiowen/code/merco
grep -n "sandbox\|confirm_edit\|snapshot" merco/tools/edit.py || true
```

Expected: no output.

- [ ] **Step 2: Run tests**

Run:

```bash
cd /home/xiowen/code/merco
python3 -m pytest tests/tools/ tests/integration/test_tool_middleware.py -v
```

Expected: pass.

- [ ] **Step 3: Update docs**

In `docs/project-vision/references/architecture-refactor-plan.md` mark:

```markdown
### 2.3 edit.py 移除 sandbox 直接依赖 ✅ 已完成
```

In `progress.md` add a short entry:

```markdown
- **edit.py 解耦（架构重构）**: EditFile 只生成 planned_edit，EditApplyMiddleware 负责 confirm/snapshot/write，tools/edit.py 不再直接依赖 sandbox。
```

- [ ] **Step 4: Commit**

```bash
cd /home/xiowen/code/merco
git add docs/project-vision/references/architecture-refactor-plan.md docs/project-vision/references/progress.md
git commit -m "docs: mark edit.py sandbox decoupling complete"
```

---

## Self-Review

**Spec coverage:**
- ✅ EditFile returns planned_edit (Task 1)
- ✅ EditApplyMiddleware confirm/snapshot/write (Task 2)
- ✅ Agent wiring (Task 3)
- ✅ Import verification + docs (Task 4)

**Behavior safety:** LLM-facing edit_file schema unchanged. Final results still success/path/diff/message or cancellation result.
