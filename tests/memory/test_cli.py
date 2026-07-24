"""CLI 记忆命令单测"""
import pytest

from merco.memory.save_pipeline import MemorySavePipeline
from merco.memory.store import MemoryStore


class FakeHooks:
    def __init__(self):
        self.events = []
    async def emit(self, event, **kwargs):
        self.events.append((event, kwargs))


@pytest.fixture
def agent_with_memory(tmp_path):
    """构造带 memory store 的 agent stub"""
    class Agent:
        pass
    a = Agent()
    a.hooks = FakeHooks()
    a._memory_store = MemoryStore(str(tmp_path / "memory"))
    a.memory_save_pipeline = MemorySavePipeline(a._memory_store, a.hooks)
    return a


@pytest.mark.asyncio
async def test_memories_lists_all(agent_with_memory, capsys):
    """空状态显示提示"""
    from cli.commands import cmd_memories
    a = agent_with_memory
    result = await cmd_memories(a, "")
    assert result is True
    out = capsys.readouterr().out
    assert "暂无记忆" in out


@pytest.mark.asyncio
async def test_memories_lists_existing(agent_with_memory, capsys):
    """已有记忆时显示列表"""
    from cli.commands import cmd_memories
    a = agent_with_memory
    a._memory_store.save("k1", "hello", tags=["[user]"])
    a._memory_store.save("k2", "world", tags=["[extracted]"])
    await cmd_memories(a, "")
    out = capsys.readouterr().out
    assert "k1" in out
    assert "k2" in out
    assert "[user]" in out


@pytest.mark.asyncio
async def test_forget_deletes_key(agent_with_memory, capsys):
    """/forget 删除已存在 key"""
    from cli.commands import cmd_forget
    a = agent_with_memory
    a._memory_store.save("k1", "hello", tags=["[user]"])
    await cmd_forget(a, "k1")
    assert a._memory_store.load("k1") is None


@pytest.mark.asyncio
async def test_forget_nonexistent_is_silent(agent_with_memory, capsys):
    """/forget 不存在 key 静默"""
    from cli.commands import cmd_forget
    a = agent_with_memory
    # 不应抛
    await cmd_forget(a, "nonexistent")
    out = capsys.readouterr().out
    # 无报错信息
    assert "Error" not in out and "错误" not in out
