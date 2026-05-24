"""CLI 主入口"""

import asyncio
import logging
import os
import readline
import signal
import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

console = Console()

app = typer.Typer(
    name="openmercury",
    help="OpenMercury - AI 驱动的自改进软件开发平台",
    add_completion=False,
)


# ── 共享的 Agent 启动逻辑 ────────────────────────────────────────────────

def _setup_agent(config_path: str | None, model: str | None, api_key: str | None, debug: bool):
    from openmercury.core.config import OpenMercuryConfig
    from openmercury.core.agent import Agent
    import openmercury
    from openmercury.tools.registry import ToolRegistry
    from openmercury.tools.file_tools import ReadFile, WriteFile
    from openmercury.tools.bash_tools import BashTool
    from openmercury.tools.mcp_tools import MCPTool as _MCPTool
    from openmercury.tools.web_tools import WebSearch as WebSearchTool, WebFetch as WebFetchTool

    if debug:
        logging.basicConfig(
            level=logging.WARNING,  # 全局默认 WARNING，不污染第三方库
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%H:%M:%S",
        )
        logging.getLogger("openmercury").setLevel(logging.DEBUG)
        console.print("[yellow]🔍 调试模式已开启[/yellow]")
    else:
        logging.basicConfig(level=logging.WARNING)

    cfg = OpenMercuryConfig.load(config_path)
    if model:
        cfg.model.model = model
    if api_key:
        cfg.model.api_key = api_key

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

    tool_registry = ToolRegistry()
    tool_registry.register(ReadFile())
    tool_registry.register(WriteFile())
    tool_registry.register(BashTool())
    tool_registry.register(_MCPTool())
    tool_registry.register(WebSearchTool())
    tool_registry.register(WebFetchTool())

    # ── 技能注册 ──
    from openmercury.skills.registry import SkillRegistry
    skill_registry = SkillRegistry()
    if cfg.skills_paths:
        skill_registry.load_from_paths(cfg.skills_paths)

    agent = Agent(config=cfg, tool_registry=tool_registry,
                  skill_registry=skill_registry)

    # 显示加载的配置来源
    import os
    config_source = "默认值"
    for candidate in ["./openmercury.json", "./.openmercury/openmercury.json",
                       os.path.expanduser("~/.config/openmercury/config.json")]:
        if os.path.exists(candidate):
            config_source = candidate
            break

    skills = skill_registry.list_skills() if skill_registry else []
    skill_line = f"技能: {len(skills)} 个已加载" if skills else "技能: 无"
    console.print(Panel(
        f"[bold green]OpenMercury v{openmercury.__version__}[/bold green]\n"
        f"模型: {cfg.model.provider}/{cfg.model.model}\n"
        f"工具: {len(tool_registry.list_tools())} 个已注册\n"
        f"{skill_line}\n"
        f"配置: [dim]{config_source}[/dim]\n\n"
        "[dim]输入消息开始对话，/help 查看命令，/exit 退出[/dim]",
        title="🚀 OpenMercury",
    ))

    return agent


# ── 上下文进度条 ──────────────────────────────────────────────────────

def _render_context_bar(stats: dict) -> str:
    """渲染 token 用量进度条"""
    max_w = 20
    filled = int(stats["ratio"] * max_w)
    if filled >= max_w:
        filled = max_w - 1
    bar = "░" * max_w
    bar = bar[:filled] + "│" + bar[filled + 1:]
    est = "~" if stats["is_estimate"] else ""
    threshold_pct = int(stats["threshold"] * 100)
    color = "dim"
    if stats["ratio"] > stats["threshold"]:
        color = "yellow"
    if stats["ratio"] > 0.95:
        color = "red"
    tool_info = f"🔧 {stats['tool_count']}/{stats['max_tool_calls']}"
    return f"  [{color}]{bar}[/{color}]  {est}{stats['current']//1024}K/{stats['max']//1024}K  {tool_info}"


# ── REPL 交互循环 ────────────────────────────────────────────────────────

def run_repl(agent):
    import termios

    try:
        old_tc = termios.tcgetattr(0)
    except termios.error:
        old_tc = None

    if old_tc is not None:
        new_tc = termios.tcgetattr(0)
        new_tc[3] = new_tc[3] & ~termios.ECHOCTL
        try:
            termios.tcsetattr(0, termios.TCSADRAIN, new_tc)
        except termios.error:
            pass

    _exit_hooks = []

    def _on_exit(fn):
        _exit_hooks.append(fn)

    def _run_exit_hooks():
        for hook in reversed(_exit_hooks):
            try:
                hook()
            except Exception:
                pass

    if old_tc is not None:
        _on_exit(lambda: termios.tcsetattr(0, termios.TCSADRAIN, old_tc))

    async def repl():
        loop = asyncio.get_running_loop()
        current_task: asyncio.Task | None = None
        exit_count = 0

        def handle_interrupt():
            nonlocal current_task, exit_count
            if current_task and not current_task.done():
                current_task.cancel()
            else:
                exit_count += 1
                if exit_count == 1:
                    console.print("\n[yellow]再按 Ctrl+C 退出，或输入 /exit。[/yellow]")
                else:
                    console.print("\n[dim]再见！[/dim]")
                    try:
                        loop.remove_signal_handler(signal.SIGINT)
                    except Exception:
                        pass
                    _run_exit_hooks()
                    os._exit(0)

        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, handle_interrupt)

        try:
            while True:
                try:
                    stats = agent.get_context_stats()
                    bar = _render_context_bar(stats)
                    user_input = await asyncio.to_thread(input, f"\n{bar}\n> ")
                    user_input = user_input.strip()
                    exit_count = 0  # 正常输入，重置计数

                    if not user_input:
                        continue

                    if user_input.startswith("/"):
                        if await handle_command(user_input, agent):
                            continue
                        else:
                            break

                    console.rule("[bold]Agent[/bold]", style="dim")
                    current_task = asyncio.current_task()
                    response = await agent.run(user_input)
                    current_task = None

                    console.print(Panel(Markdown(response), border_style="dim"))
                    console.rule(style="dim")

                except asyncio.CancelledError:
                    console.rule(style="dim")
                    console.print("\n[dim]操作已取消。再按一次 Ctrl+C 退出。[/dim]")
                    current_task = None
                except EOFError:
                    console.print("\n[dim]再见！[/dim]")
                    break
                except KeyboardInterrupt:
                    console.print("\n[dim]再见！[/dim]")
                    break
                except Exception as e:
                    current_task = None
                    console.print(f"[red]错误: {e}[/red]")
        finally:
            for sig in (signal.SIGINT, signal.SIGTERM):
                try:
                    loop.remove_signal_handler(sig)
                except (NotImplementedError, RuntimeError):
                    pass

    try:
        asyncio.run(repl())
    except KeyboardInterrupt:
        pass
    finally:
        _run_exit_hooks()


# ── 回调：无子命令时进入交互模式 ─────────────────────────────────────────

@app.callback(invoke_without_command=True)
def main_callback(
    ctx: typer.Context,
    config: str = typer.Option(None, "--config", "-c", help="配置文件路径"),
    model: str = typer.Option(None, "--model", "-m", help="指定模型"),
    api_key: str = typer.Option(None, "--api-key", "-k", help="API Key"),
    debug: bool = typer.Option(False, "--debug", "-d", help="开启调试日志"),
):
    if ctx.invoked_subcommand is not None:
        return
    agent = _setup_agent(config, model, api_key, debug)
    run_repl(agent)


# ── 子命令 ────────────────────────────────────────────────────────────────

@app.command("run")
def run_cmd(
    config: str = typer.Option(None, "--config", "-c", help="配置文件路径"),
    model: str = typer.Option(None, "--model", "-m", help="指定模型"),
    api_key: str = typer.Option(None, "--api-key", "-k", help="API Key"),
    debug: bool = typer.Option(False, "--debug", "-d", help="开启调试日志"),
):
    agent = _setup_agent(config, model, api_key, debug)
    run_repl(agent)


@app.command("init")
def init_cmd(path: str = typer.Argument(".", help="项目路径")):
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


# ── 命令处理 ──────────────────────────────────────────────────────────────

async def handle_command(cmd: str, agent) -> bool:
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

    elif command == "/context":
        stats = agent.get_context_stats()
        console.print(_render_context_bar(stats))
        console.print(f"  阈值: {int(stats['threshold']*100)}%  |  模型推算: {'是' if stats['is_estimate'] else '否（API 实测）'}")
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


if __name__ == "__main__":
    app()
