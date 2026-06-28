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
