"""CLI 测试共享 fixture — capture_console / fake_agent"""
import io
from unittest.mock import MagicMock, AsyncMock

import pytest
from rich.console import Console


class _CaptureConsole(Console):
    """Console 子类：截获 print() 的原始 markup 输入，同时写入另一 buffer。"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._markup_buf = io.StringIO()

    def print(self, *args, **kwargs):
        for a in args:
            self._markup_buf.write(str(a))
        return super().print(*args, **kwargs)

    def get_markup(self) -> str:
        """返回 print() 接收到的原始 markup 文本。"""
        return self._markup_buf.getvalue()


@pytest.fixture
def capture_console(monkeypatch):
    """替换 cli.main 和 cli.commands 的全局 console，同时捕获 ANSI 输出和原始 markup。

    Returns:
        (_CaptureConsole, io.StringIO):
            (capture 对象, ANSI 内容缓冲)
            — capture 提供 get_markup() 方法，返回 print() 接收到的原始 markup 文本
    """
    from cli import main, commands

    buf = io.StringIO()
    capture = _CaptureConsole(
        file=buf,
        force_terminal=True,
        width=120,
        record=True,
    )
    monkeypatch.setattr(main, "console", capture)
    monkeypatch.setattr(commands, "console", capture)
    return capture, buf


def make_fake_agent(
    run_return=None,
    run_side_effect=None,
    config_overrides=None,
):
    """构造一个 MagicMock agent，可控制 agent.run() 行为。

    Args:
        run_return: agent.run() 的返回值
        run_side_effect: agent.run() 的 side_effect（异常/返回值序列）
        config_overrides: 覆盖 agent.config 的字段，如
            {"streaming": False, "stream_content": False, ...}

    Returns:
        MagicMock: 形如真实 Agent 的 mock；config.model 有 provider/model 属性
    """
    agent = MagicMock()
    config = MagicMock()
    config.streaming = False
    config.stream_content = False
    config.model.provider = "openai"
    config.model.model = "gpt-4o"
    config.sandbox_mode = "local"
    config.fork_reset_observer = True
    if config_overrides:
        for k, v in config_overrides.items():
            setattr(config, k, v)
    agent.config = config

    if run_side_effect is not None:
        agent.run = AsyncMock(side_effect=run_side_effect)
    elif run_return is not None:
        agent.run = AsyncMock(return_value=run_return)
    else:
        agent.run = AsyncMock(return_value="default response")

    # token tracker / session 占位（dashboard 可能调用）
    agent.get_context_stats = MagicMock(return_value={
        "ratio": 0.0, "threshold": 0.8, "current": 0, "max": 1000,
        "is_estimate": False,
    })
    agent.session = MagicMock()
    agent.session.id = "test-session-id"
    agent.session.title = "测试会话"
    agent.session.messages = []
    agent.session.metadata = {}
    agent.session.save = MagicMock()

    # skill_registry / tool_registry / observer
    agent.skill_registry = None
    agent.tool_registry = None
    agent.observer = MagicMock()
    agent.observer.reset = MagicMock()
    agent.observer.save = MagicMock()
    agent.observer.snapshot = MagicMock(return_value={})
    agent.observer.report = MagicMock(return_value="report content")

    return agent


@pytest.fixture
def fake_agent_factory():
    """暴露 make_fake_agent 工厂"""
    return make_fake_agent
