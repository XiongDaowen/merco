"""DashboardSection 与 Dashboard 渲染测试"""

from unittest.mock import MagicMock

from cli.main import (
    ConfigSection,
    Dashboard,
    HintSection,
    ModelSection,
    SessionSection,
    SkillsSection,
    ToolsSection,
    WelcomeSection,
)
from tests.cli.conftest import make_fake_agent


def test_welcome_section_includes_version():
    """首页应展示版本号"""
    section = WelcomeSection()
    text = section.render(agent=None)
    assert "Mercury Code" in text
    assert "v" in text  # 含版本号标记


def test_model_section_shows_provider_and_model():
    """ModelSection 显示 provider/model"""
    section = ModelSection()
    agent = make_fake_agent()
    text = section.render(agent)
    assert "openai" in text
    assert "gpt-4o" in text


def test_tools_section_shows_dim_none_when_registry_missing():
    """tool_registry=None 时显示[dim]无[/dim]"""
    section = ToolsSection()
    agent = make_fake_agent()
    agent.tool_registry = None
    text = section.render(agent)
    assert "工具" in text
    assert "[dim]无[/dim]" in text


def test_tools_section_shows_dim_none_when_empty():
    """tool_registry 空时显示[dim]无[/dim]"""
    section = ToolsSection()
    agent = make_fake_agent()
    registry = MagicMock()
    registry.list_tools = MagicMock(return_value=[])
    agent.tool_registry = registry
    text = section.render(agent)
    assert "[dim]无[/dim]" in text


def test_tools_section_shows_active_tool_names():
    """显示所有 active 工具"""
    section = ToolsSection(max_display=10)
    agent = make_fake_agent()
    t1 = MagicMock()
    t1.name = "read_file"
    t1.check = MagicMock(return_value=True)
    t1.toolset = "builtin"
    t1.description = "读文件"
    t2 = MagicMock()
    t2.name = "write_file"
    t2.check = MagicMock(return_value=True)
    t2.toolset = "builtin"
    t2.description = "写文件"
    registry = MagicMock()
    registry.list_tools = MagicMock(return_value=[t1, t2])
    agent.tool_registry = registry
    text = section.render(agent)
    assert "read_file" in text
    assert "write_file" in text


def test_tools_section_truncates_with_etc_marker():
    """超过 max_display 时显示[dim]等 N 个[/dim]"""
    section = ToolsSection(max_display=2)
    agent = make_fake_agent()
    tools = []
    for i in range(5):
        t = MagicMock()
        t.name = f"tool_{i}"
        t.check = MagicMock(return_value=True)
        t.toolset = "builtin"
        t.description = f"描述 {i}"
        tools.append(t)
    registry = MagicMock()
    registry.list_tools = MagicMock(return_value=tools)
    agent.tool_registry = registry
    text = section.render(agent)
    assert "tool_0" in text
    assert "tool_1" in text
    assert "[dim]等 5 个[/dim]" in text


def test_skills_section_shows_dim_none_when_registry_missing():
    """skill_registry=None 时显示[dim]无[/dim]"""
    section = SkillsSection()
    agent = make_fake_agent()
    agent.skill_registry = None
    text = section.render(agent)
    assert "技能" in text
    assert "[dim]无[/dim]" in text


def test_skills_section_shows_names_and_truncates():
    """SkillsSection 列出前 max_display 个，超出截断"""
    section = SkillsSection(max_display=2)
    agent = make_fake_agent()
    registry = MagicMock()
    registry.list_skills = MagicMock(
        return_value=[
            {"name": "brainstorming", "description": "a"},
            {"name": "test", "description": "b"},
            {"name": "review", "description": "c"},
            {"name": "debug", "description": "d"},
        ]
    )
    agent.skill_registry = registry
    text = section.render(agent)
    assert "brainstorming" in text
    assert "test" in text
    assert "review" not in text
    assert "[dim]等 4 个[/dim]" in text


def test_config_section_shows_default_value():
    """ConfigSection 默认显示'默认值'"""
    section = ConfigSection()
    text = section.render(agent=None, config_source="默认值")
    assert "默认值" in text


def test_config_section_shows_path_when_provided():
    """ConfigSection 接受自定义 config_source"""
    section = ConfigSection()
    text = section.render(agent=None, config_source="/tmp/my.json")
    assert "/tmp/my.json" in text


def test_session_section_shows_existing_session():
    """SessionSection 显示带消息数的会话"""
    section = SessionSection()
    agent = make_fake_agent()
    agent.session.messages = [1, 2, 3]  # 3 条
    text = section.render(agent)
    assert "测试会话" in text
    assert "3 条消息" in text


def test_session_section_shows_new_session_when_no_messages():
    """SessionSection 无消息时显示新会话"""
    section = SessionSection()
    agent = make_fake_agent()
    agent.session.messages = []
    text = section.render(agent)
    assert "新会话" in text


def test_hint_section_shows_help_text():
    """HintSection 提示用户输入消息"""
    section = HintSection()
    text = section.render(agent=None)
    assert "/help" in text
    assert "/exit" in text


def test_dashboard_renders_all_sections_in_registration_order():
    """Dashboard 按 use() 顺序拼接所有区块输出"""
    dashboard = Dashboard().use(WelcomeSection()).use(ModelSection()).use(HintSection())
    agent = make_fake_agent()
    text = dashboard.render(agent)
    # 三段都应该存在
    assert "Mercury Code" in text
    assert "openai" in text
    assert "/help" in text


def test_dashboard_skips_section_returning_none():
    """render() 返回 None 或空字符串时跳过"""

    class EmptySection:
        name = "empty"

        def render(self, agent, **ctx):
            return None

    dashboard = Dashboard().use(WelcomeSection()).use(EmptySection()).use(HintSection())
    agent = make_fake_agent()
    text = dashboard.render(agent)
    assert "Mercury Code" in text
    assert "/help" in text


def test_dashboard_section_render_failure_does_not_crash():
    """某个区块 render() 抛异常时，整个 Dashboard 不挂，显示失败标记"""

    class CrashSection:
        name = "crash"

        def render(self, agent, **ctx):
            raise RuntimeError("boom")

    dashboard = Dashboard().use(WelcomeSection()).use(CrashSection())
    agent = make_fake_agent()
    text = dashboard.render(agent)
    assert "Mercury Code" in text
    assert "crash" in text
    assert "渲染失败" in text
