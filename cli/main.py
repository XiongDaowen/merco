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


# ── 启动首页 Dashboard ──────────────────────────────────────────────

from abc import ABC, abstractmethod
import openmercury

class DashboardSection(ABC):
    """首页展示区块基类。新增条目：继承 + 实现 render() + dashboard.use()"""
    name: str = ""

    @abstractmethod
    def render(self, agent, **ctx) -> str | None:
        """返回一行 Rich 标记文本，None 则跳过"""
        ...


class WelcomeSection(DashboardSection):
    name = "welcome"
    def render(self, agent, **ctx) -> str:
        return f"[bold green]OpenMercury v{openmercury.__version__}[/bold green]"


class ModelSection(DashboardSection):
    name = "model"
    def render(self, agent, **ctx) -> str:
        return f"模型: {agent.config.model.provider}/{agent.config.model.model}"


class ToolsSection(DashboardSection):
    name = "tools"
    max_display: int = 5

    def render(self, agent, **ctx) -> str:
        tools = agent.tool_registry.list_tools() if agent.tool_registry else []
        active = [t.name for t in tools if t.check()]
        if not active:
            return "工具: [dim]无[/dim]"
        shown = active[:self.max_display]
        line = f"工具: [bold]{', '.join(shown)}[/bold]"
        if len(active) > self.max_display:
            line += f" [dim]等 {len(active)} 个[/dim]"
        return line


class SkillsSection(DashboardSection):
    name = "skills"
    max_display: int = 3

    def render(self, agent, **ctx) -> str:
        registry = getattr(agent, "skill_registry", None)
        if not registry:
            return "技能: [dim]无[/dim]"
        skills = registry.list_skills()
        if not skills:
            return "技能: [dim]无[/dim]"
        names = [s["name"] for s in skills[:self.max_display]]
        line = f"技能: [bold]{', '.join(names)}[/bold]"
        if len(skills) > self.max_display:
            line += f" [dim]等 {len(skills)} 个[/dim]"
        return line


class ConfigSection(DashboardSection):
    name = "config"

    def render(self, agent, **ctx) -> str:
        return f"配置: [dim]{ctx.get('config_source', '默认值')}[/dim]"


class HintSection(DashboardSection):
    name = "hint"

    def render(self, agent, **ctx) -> str:
        return "[dim]输入消息开始对话，/help 查看命令，/exit 退出[/dim]"


class Dashboard:
    """首页渲染器。按 use() 顺序渲染各区块。"""
    def __init__(self):
        self._sections: list[DashboardSection] = []

    def use(self, section: DashboardSection) -> "Dashboard":
        self._sections.append(section)
        return self

    def render(self, agent, **ctx) -> str:
        parts = []
        for s in self._sections:
            try:
                line = s.render(agent, **ctx)
                if line:
                    parts.append(line)
            except Exception:
                parts.append(f"[dim]({s.name}: 渲染失败)[/dim]")
        return "\n".join(parts)


# ── 共享的 Agent 启动逻辑 ────────────────────────────────────────────────

def _setup_agent(config_path: str | None, model: str | None, api_key: str | None, debug: bool):
    from openmercury.core.config import OpenMercuryConfig
    from openmercury.core.agent import Agent
    import openmercury
    from openmercury.tools import discover_tools, tool_registry
    discover_tools()

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

    # tools auto-registered via discover_tools()

    # ── 技能注册 ──
    from openmercury.skills.registry import SkillRegistry
    skill_registry = SkillRegistry()
    if cfg.skills_paths:
        skill_registry.load_from_paths(cfg.skills_paths)

    # 注入 skill_registry 给 SkillViewTool（动态描述 + 可用性检查）
    sv = tool_registry.get("skill_view")
    if sv and hasattr(sv, "set_skill_registry"):
        sv.set_skill_registry(skill_registry)

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

    dashboard = (Dashboard()
        .use(WelcomeSection())
        .use(ModelSection())
        .use(ToolsSection(max_display=5))
        .use(SkillsSection(max_display=3))
        .use(ConfigSection())
        .use(HintSection()))

    console.print(Panel(
        dashboard.render(agent, config_source=config_source),
        title="🚀 OpenMercury",
    ))
    return agent


# ── 上下文进度条 ──────────────────────────────────────────────────────

def _render_context_bar(stats: dict) -> str:
    """渲染 token 用量进度条 — 阈值标记在中间"""
    w = 10
    thresh_p = int(stats["threshold"] * w)
    filled_n = int(stats["ratio"] * w)
    bar = "▕"
    for i in range(w):
        if i == thresh_p:
            bar += "│"
        elif i < filled_n:
            bar += "█"
        else:
            bar += "░"
    bar += "▏"

    color = "dim"
    if stats["ratio"] > stats["threshold"]:
        color = "yellow"
    if stats["ratio"] > 0.95:
        color = "red"
    est = "~" if stats["is_estimate"] else ""
    tool_info = f"🔧 {stats['tool_count']}/{stats['max_tool_calls']}"
    cur = stats["current"]; mx = stats["max"]
    def _f(n): return str(n) if n < 1024 else f"{n/1024:.1f}K"
    return f"  [{color}]{bar}[/{color}]  {est}{_f(cur)}/{_f(mx)}  {tool_info}"


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
                    console.print(f"\n{bar}")
                    user_input = await asyncio.to_thread(input, "> ")
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
            "/tools    - 列出可用工具\n"
            "/context  - 上下文用量\n"
            "/skills   - 列出已加载技能",
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
