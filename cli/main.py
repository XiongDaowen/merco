"""CLI 主入口"""

import typer

app = typer.Typer(help="OpenMercury - AI 驱动的自改进软件开发平台")


@app.command()
def run(
    config: str = typer.Option(None, "--config", "-c", help="配置文件路径"),
    model: str = typer.Option(None, "--model", "-m", help="指定模型"),
):
    """启动 OpenMercury"""
    from openmercury.core.config import OpenMercuryConfig
    from openmercury.core.agent import Agent

    cfg = OpenMercuryConfig.load(config)
    if model:
        cfg.model.model = model

    agent = Agent(config=cfg)
    print("OpenMercury started. Type your message or /help for commands.")


@app.command()
def init(path: str = typer.Argument(".", help="项目路径")):
    """初始化项目配置"""
    from pathlib import Path

    config_path = Path(path) / "openmercury.json"
    if config_path.exists():
        print(f"Config already exists at {config_path}")
        return

    from openmercury.core.config import OpenMercuryConfig

    cfg = OpenMercuryConfig()
    cfg.save(str(config_path))
    print(f"Created config at {config_path}")


@app.command()
def skills(
    list: bool = typer.Option(False, "--list", "-l", help="列出已加载技能"),
    path: str = typer.Option(None, "--path", "-p", help="技能目录路径"),
):
    """管理技能"""
    from openmercury.skills.loader import SkillLoader
    from openmercury.skills.registry import SkillRegistry

    if list:
        registry = SkillRegistry()
        if path:
            registry.load_from_paths([path])
        else:
            registry.load_from_paths(["./.opencode/skills", "~/.config/openmercury/skills"])

        skills = registry.list_skills()
        if skills:
            print(f"Loaded {len(skills)} skills:")
            for skill in skills:
                print(f"  - {skill['name']}: {skill['description']}")
        else:
            print("No skills loaded.")


if __name__ == "__main__":
    app()
