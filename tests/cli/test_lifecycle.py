"""CLI 生命周期文案测试 — 启动 banner、调试模式、配置错误、退出"""
from unittest.mock import MagicMock, AsyncMock, patch

import pytest
import typer

from cli import main
from tests.cli.conftest import make_fake_agent


@pytest.mark.asyncio
async def test_setup_agent_with_debug_prints_yellow_banner(capture_console):
    """debug=True 时输出 [yellow]🔍 调试模式已开启[/yellow]"""
    capture, buf = capture_console

    with patch("merco.tools.discover_tools", MagicMock()):
        with patch("merco.core.config.MercoConfig") as mock_cfg_cls:
            cfg = MagicMock()
            cfg.model.api_key = "sk-test"
            cfg.model.provider = "openai"
            cfg.model.model = "gpt-4o"
            cfg.sandbox_mode = "local"
            mock_cfg_cls.load = MagicMock(return_value=cfg)

            with patch("merco.core.agent.Agent") as mock_agent_cls:
                mock_agent = make_fake_agent()
                mock_agent_cls.create = AsyncMock(return_value=mock_agent)

                with patch("merco.skills.builtin.install_builtin_skills"):
                    try:
                        await main._setup_agent(None, None, None, debug=True)
                    except Exception:
                        pass  # 后续路径可能仍有副作用，但前段文案已打出

    assert "[yellow]🔍 调试模式已开启[/yellow]" in capture.get_markup()


@pytest.mark.asyncio
async def test_setup_agent_missing_api_key_prints_panel(capture_console, monkeypatch):
    """无 API Key 时输出 yellow Panel 引导用户配置"""
    capture, buf = capture_console
    monkeypatch.setattr("builtins.input", lambda *a, **kw: "n")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    with patch("merco.tools.discover_tools", MagicMock()):
        with patch("merco.core.config.MercoConfig") as mock_cfg_cls:
            cfg = MagicMock()
            cfg.model.api_key = None
            cfg.model.provider = "openai"
            cfg.model.model = "gpt-4o"
            mock_cfg_cls.load = MagicMock(return_value=cfg)

            with pytest.raises(typer.Exit):
                await main._setup_agent(None, None, None, debug=False)

    text = capture.export_text()
    assert "需要配置" in text
    assert "未配置 API Key" in text


def test_init_command_existing_config_prints_yellow(tmp_path):
    """merco init 配置已存在时打印黄色提示"""
    from typer.testing import CliRunner

    config_path = tmp_path / "merco.json"
    config_path.write_text("{}")
    runner = CliRunner()
    result = runner.invoke(main.app, ["init", str(tmp_path)])
    assert result.exit_code == 0
    text = str(result.stdout) if result.stdout else ""
    assert "配置已存在" in text


def test_init_command_creates_config(tmp_path):
    """merco init 在空目录创建配置"""
    from typer.testing import CliRunner

    config_path = tmp_path / "merco.json"
    if config_path.exists():
        config_path.unlink()

    runner = CliRunner()
    result = runner.invoke(main.app, ["init", str(tmp_path)])
    out = str(result.stdout) if result.stdout else ""
    assert "Traceback" not in out
    assert config_path.exists()
    assert "已创建配置" in out


def test_dashboard_renders_key_info():
    """Dashboard 调用 render 返回欢迎信息与帮助提示"""
    from cli.main import Dashboard, WelcomeSection, HintSection

    dashboard = (Dashboard()
        .use(WelcomeSection())
        .use(HintSection()))
    agent = make_fake_agent()
    dashboard_text = dashboard.render(agent)
    assert "Mercury Code" in dashboard_text
    assert "/help" in dashboard_text
