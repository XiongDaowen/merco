"""CommandRegistry 测试"""

import pytest

from cli.registry import CommandRegistry, cmd_registry


@pytest.fixture
def fresh_registry():
    """每次测试获得空注册表"""
    return CommandRegistry()


def test_register_and_get(fresh_registry):
    """注册 /test，验证 get 返回正确定义"""
    fresh_registry.register("/test", "测试命令", lambda: None)
    cmd = fresh_registry.get("/test")
    assert cmd is not None
    assert cmd.name == "/test"
    assert cmd.description == "测试命令"
    assert cmd.group == "general"


def test_match_prefix(fresh_registry):
    """注册 /fork, /foo，match /f 返回两个"""
    fresh_registry.register("/fork", "fork 命令", lambda: None)
    fresh_registry.register("/foo", "foo 命令", lambda: None)
    results = fresh_registry.match("/f")
    names = [c.name for c in results]
    assert len(results) == 2
    assert "/foo" in names
    assert "/fork" in names


def test_match_exact(fresh_registry):
    """match /fork 返回恰好 1 个"""
    fresh_registry.register("/fork", "fork 命令", lambda: None)
    fresh_registry.register("/foo", "foo 命令", lambda: None)
    results = fresh_registry.match("/fork")
    assert len(results) == 1
    assert results[0].name == "/fork"


def test_get_all_grouped(fresh_registry):
    """注册不同分组的命令，验证分组过滤"""
    fresh_registry.register("/a", "命令 A", lambda: None, group="group1")
    fresh_registry.register("/b", "命令 B", lambda: None, group="group2")
    fresh_registry.register("/c", "命令 C", lambda: None, group="group1")

    all_cmds = fresh_registry.get_all()
    assert len(all_cmds) == 3

    g1 = fresh_registry.get_all("group1")
    assert len(g1) == 2
    assert {c.name for c in g1} == {"/a", "/c"}

    g2 = fresh_registry.get_all("group2")
    assert len(g2) == 1
    assert g2[0].name == "/b"


def test_sub_commands(fresh_registry):
    """注册带 sub 字典的命令，验证子命令可访问"""
    fresh_registry.register(
        "/skill", "技能命令", lambda: None,
        sub={"view": "查看技能", "list": "列出技能"},
    )
    cmd = fresh_registry.get("/skill")
    assert cmd is not None
    assert cmd.sub_commands == {"view": "查看技能", "list": "列出技能"}


def test_get_help_text(fresh_registry):
    """验证 help 文本包含命令名和描述"""
    fresh_registry.register("/help", "显示帮助", lambda: None)
    fresh_registry.register("/exit", "退出程序", lambda: None)
    text = fresh_registry.get_help_text()
    assert "/help" in text
    assert "/exit" in text
    assert "显示帮助" in text
    assert "退出程序" in text


def test_module_singleton(monkeypatch):
    """模块级 cmd_registry 是 CommandRegistry 实例，且注册表可通过 monkeypatch 重置为干净状态。

    注：'空' 不是单例的不变性质——其他测试模块（如 test_commands_ui.py）import cli.commands
    会触发所有 @cmd_registry.register 装饰器，污染全局注册表。本测试用 monkeypatch 临时清空
    以验证注册表确实可以是空状态（验证类型而非具体数量）。
    """
    # 临时清空注册表（不验证 len == 0，因为其他测试可能先 import cli.commands）
    monkeypatch.setattr(cmd_registry, "_commands", {})
    assert isinstance(cmd_registry, CommandRegistry)
    assert len(cmd_registry) == 0
