"""EditFile planner + EditApplyMiddleware 单测"""

import pytest

from merco.tools.edit import EditFile
from merco.tools.middleware import EditApplyMiddleware, ToolContext


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
    monkeypatch.setattr(
        "merco.tools.middleware.snapshot.track",
        lambda path, old: (_ for _ in ()).throw(AssertionError("should not track")),
    )

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
