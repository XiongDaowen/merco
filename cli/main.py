"""CLI 主入口"""

import asyncio
import typer
import os
from rich.console import Console
from rich.panel import Panel

console = Console()

app = typer.Typer(
    name="openmercury",
    help="OpenMercury - AI 驱动的自改进软件开发平台",
    add_completion=False,
)


@app.command("run")
def run_cmd(
    config: str = typer.Option(None, "--config", "-c", help="配置文件路径"),
    model: str = typer.Option(None, "--model", "-m", help="指定模型"),
    api_key: str = typer.Option(None, "--api-key", "-k", help="API Key"),
):
    """启动 OpenMercury 交互模式"""
    from openmercury.core.config import OpenMercuryConfig
    from openmercury.core.agent import Agent
    from openmercury.tools.registry import ToolRegistry
    from openmercury.tools.file_tools import ReadFile, WriteFile
    from openmercury.tools.bash_tools import BashTool

    # 加载配置
    cfg = OpenMercuryConfig.load(config)

    if model:
        cfg.model.model = model
    if api_key:
        cfg.model.api_key = api_key

    # 检查 API Key
    if not cfg.model.api_key:
        env_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("OPENROUTER_API_KEY")
        if env_key:
            cfg.model.api_key = env_key
        else:
            console.print(Panel(
                "[red]未找到 API Key。请设置：\n"
                "1. 配置文件中设置 model.api_key\n"
                "2. 或设置环境变量 OPENAI_API_KEY / OPENROUTER_API_KEY\n"
                "3. 或使用 --api-key 参数[/red]",
                title="配置错误",
            ))
            raise typer.Exit(1)

    # 初始化工具
    tool_registry = ToolRegistry()
    tool_registry.register(ReadFile())
    tool_registry.register(WriteFile())
    tool_registry.register(BashTool())

    # 创建 Agent
    agent = Agent(config=cfg, tool_registry=tool_registry)

    # 显示欢迎信息
    console.print(Panel(
        f"[bold green]OpenMercury v{cfg.__class__.__module__.split('.')[0]}[/bold green]\n"
        f"模型: {cfg.model.provider}/{cfg.model.model}\n"
        f"工具: {', '.join(t.name for t in tool_registry.list_tools())}\n\n"
        "[dim]输入消息开始对话，/help 查看命令，/exit 退出[/dim]",
        title="🚀 OpenMercury",
    ))

    # REPL 循环
    async def repl():
        while True:
            try:
                # 获取用户输入
                user_input = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: input("\n> ")
                )
                user_input = user_input.strip()

                if not user_input:
                    continue

                # 处理命令
                if user_input.startswith("/"):
                    if await handle_command(user_input, agent):
                        continue
                    else:
                        break

                # 调用 Agent
                with console.status("[bold blue]思考中...[/bold blue]"):
                    response = await agent.run(user_input)

                # 显示回复
                console.print(f"\n{response}")

            except KeyboardInterrupt:
                console.print("\n[dim]按 /exit 退出[/dim]")
            except EOFError:
                break
            except Exception as e:
                console.print(f"[red]错误: {e}[/red]")

    asyncio.run(repl())


async def handle_command(cmd: str, agent) -> bool:
    """处理斜杠命令，返回 True 继续循环，False 退出"""
    parts = cmd.split(maxsplit=1)
    command = parts[0].lower()

    if command in ("/exit", "/quit", "/q"):
        console.print("[dim]再见！[/dim]")
        return False

    elif command == "/help":
        console.print(Panel(
            "[bold]可用命令[/bold]\n\n"
            "/help     - 显示此帮助\n"
            "/exit     - 退出\n"
            "/new      - 新会话\n"
            "/model    - 显示当前模型\n"
            "/tools    - 列出可用工具",
            title="帮助",
        ))
        return True

    elif command == "/new":
        agent.reset()
        console.print("[dim]已开启新会话[/dim]")
        return True

    elif command == "/model":
        console.print(f"当前模型: {agent.config.model.provider}/{agent.config.model.model}")
        return True

    elif command == "/tools":
        tools = agent.tool_registry.list_tools() if agent.tool_registry else []
        if tools:
            console.print("[bold]可用工具:[/bold]")
            for tool in tools:
                console.print(f"  - {tool.name}: {tool.description}")
        else:
            console.print("无可用工具")
        return True

    else:
        console.print(f"[dim]未知命令: {command}，输入 /help 查看帮助[/dim]")
        return True


@app.command("init")
def init_cmd(path: str = typer.Argument(".", help="项目路径")):
    """初始化项目配置"""
    from pathlib import Path
    from openmercury.core.config import OpenMercuryConfig

    config_path = Path(path) / "openmercury.json"
    if config_path.exists():
        console.print(f"[yellow]配置已存在: {config_path}[/yellow]")
        return

    cfg = OpenMercuryConfig()
    cfg.save(str(config_path))
    console.print(f"[green]已创建配置: {config_path}[/green]")


@app.command("skills")
def skills_cmd(
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
            console.print(f"[bold]已加载 {len(skills)} 个技能:[/bold]")
            for skill in skills:
                console.print(f"  - {skill['name']}: {skill['description']}")
        else:
            console.print("未加载任何技能")


if __name__ == "__main__":
    app()
