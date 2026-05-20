"""CLI 主入口"""

import asyncio
import signal
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
    debug: bool = typer.Option(False, "--debug", "-d", help="开启调试日志"),
):
    """启动 OpenMercury 交互模式"""
    import logging
    from openmercury.core.config import OpenMercuryConfig
    from openmercury.core.agent import Agent
    from openmercury.tools.registry import ToolRegistry
    from openmercury.tools.file_tools import ReadFile, WriteFile
    from openmercury.tools.bash_tools import BashTool

    # 配置日志级别
    if debug:
        logging.basicConfig(
            level=logging.DEBUG,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%H:%M:%S",
        )
        logging.getLogger("openmercury").setLevel(logging.DEBUG)
        console.print("[yellow]🔍 调试模式已开启[/yellow]")
    else:
        logging.basicConfig(level=logging.WARNING)

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
        loop = asyncio.get_event_loop()
        current_task: asyncio.Task | None = None

        def handle_interrupt():
            """SIGINT 处理：取消正在运行的任务并退出"""
            nonlocal current_task
            console.print("\n[yellow]正在退出...[/yellow]")
            if current_task and not current_task.done():
                current_task.cancel()
            # 退出循环
            loop.call_soon(loop.stop)

        # 注册信号处理
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, handle_interrupt)

        while True:
            try:
                # 使用 asyncio.to_thread 替代 run_in_executor（Python 3.9+）
                user_input = await asyncio.to_thread(input, "\n> ")
                user_input = user_input.strip()

                if not user_input:
                    continue

                # 处理命令
                if user_input.startswith("/"):
                    if await handle_command(user_input, agent):
                        continue
                    else:
                        break

                # 调用 Agent（可被 Ctrl+C 中断）
                with console.status("[bold blue]思考中...[/bold blue]"):
                    current_task = asyncio.current_task()
                    response = await agent.run(user_input)
                    current_task = None

                # 显示回复
                console.print(f"\n{response}")

            except asyncio.CancelledError:
                # Ctrl+C 取消操作
                console.print("\n[dim]操作已取消。再按一次退出。[/dim]")
                current_task = None
            except EOFError:
                break
            except KeyboardInterrupt:
                # 直接退出
                console.print("\n[dim]再见！[/dim]")
                break
            except Exception as e:
                current_task = None
                console.print(f"[red]错误: {e}[/red]")

    try:
        asyncio.run(repl())
    finally:
        # 清理信号处理器
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.remove_signal_handler(sig)


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
            registry.load_from_paths(["./.openmercury/skills", "~/.config/openmercury/skills"])

        skills = registry.list_skills()
        if skills:
            console.print(f"[bold]已加载 {len(skills)} 个技能:[/bold]")
            for skill in skills:
                console.print(f"  - {skill['name']}: {skill['description']}")
        else:
            console.print("未加载任何技能")


if __name__ == "__main__":
    app()
