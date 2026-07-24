"""PromptArea 与 ContextBar 渲染测试"""

from unittest.mock import MagicMock

from cli.main import (
    ContextBar,
    PromptArea,
)
from tests.cli.conftest import make_fake_agent


def test_prompt_area_empty_returns_empty_pre_and_default_prompt():
    """无装饰器时 pre_text 为空，prompt 为默认 >"""
    area = PromptArea()
    agent = make_fake_agent()
    pre, prompt = area.render(agent)
    assert pre == ""
    assert prompt == "> "


def test_context_bar_renders_session_and_token_info():
    """ContextBar 渲染会话标题 + token 数"""
    bar = ContextBar()
    agent = make_fake_agent()
    agent.get_context_stats = MagicMock(
        return_value={
            "ratio": 0.5,
            "threshold": 0.8,
            "current": 500,
            "max": 1000,
            "is_estimate": False,
        }
    )
    text = bar.render(agent)
    assert "测试会话" in text
    assert "500" in text
    assert "1.0K" in text
    assert "gpt-4o" in text


def test_context_bar_shows_estimate_with_tilde():
    """is_estimate=True 时数字带 ~ 前缀"""
    bar = ContextBar()
    agent = make_fake_agent()
    agent.get_context_stats = MagicMock(
        return_value={
            "ratio": 0.1,
            "threshold": 0.8,
            "current": 500,
            "max": 1000,
            "is_estimate": True,
        }
    )
    text = bar.render(agent)
    assert "~500" in text


def test_context_bar_color_red_when_ratio_above_95_percent():
    """ratio > 0.95 时颜色为 red"""
    bar = ContextBar()
    agent = make_fake_agent()
    agent.get_context_stats = MagicMock(
        return_value={
            "ratio": 0.99,
            "threshold": 0.8,
            "current": 990,
            "max": 1000,
            "is_estimate": False,
        }
    )
    text = bar.render(agent)
    assert "[red]" in text


def test_context_bar_extra_appends_info():
    """extra() 追加的字符串出现在输出"""
    bar = ContextBar().extra("EXTRA_INFO")
    agent = make_fake_agent()
    text = bar.render(agent)
    assert "EXTRA_INFO" in text


def test_prompt_area_renders_decorators_in_registration_order():
    """PromptArea 按 use() 顺序拼接"""

    class Deco1:
        name = "deco1"

        def render(self, agent):
            return "FIRST"

        def get_prompt(self):
            return "1> "

    class Deco2:
        name = "deco2"

        def render(self, agent):
            return "SECOND"

        def get_prompt(self):
            return "2> "

    area = PromptArea().use(Deco1()).use(Deco2())
    agent = make_fake_agent()
    pre, prompt = area.render(agent)
    # 第一个在前，第二个在后
    assert pre.index("FIRST") < pre.index("SECOND")
    # prompt 来自最后一个装饰器
    assert prompt == "2> "


def test_prompt_area_decorator_failure_does_not_crash():
    """某装饰器 render 抛异常时，其他装饰器仍渲染"""

    class CrashDeco:
        name = "crash"

        def render(self, agent):
            raise RuntimeError("boom")

        def get_prompt(self):
            return "c> "

    area = PromptArea().use(ContextBar()).use(CrashDeco())
    agent = make_fake_agent()
    pre, prompt = area.render(agent)
    assert "测试会话" in text_safe(pre)  # ContextBar 仍渲染
    assert "crash" in pre
    assert "render failed" in pre


def text_safe(s):
    return s if isinstance(s, str) else s.decode("utf-8", errors="ignore")
