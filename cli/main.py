"""CLI 主入口"""

import asyncio
import logging
import os
import signal
import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from cli.registry import cmd_registry

console = Console()

app = typer.Typer(
    name="merco",
    help="Mercury Code — AI 驱动的自改进软件开发平台",
    add_completion=False,
)


# ── 启动首页 Dashboard ──────────────────────────────────────────────

from abc import ABC, abstractmethod
import merco

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
        return f"[bold green]Mercury Code v{merco.__version__}[/bold green]"


class ModelSection(DashboardSection):
    name = "model"
    def render(self, agent, **ctx) -> str:
        return f"模型: {agent.config.model.provider}/{agent.config.model.model}"


class ToolsSection(DashboardSection):
    name = "tools"

    def __init__(self, max_display: int = 5):
        self.max_display = max_display

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

    def __init__(self, max_display: int = 3):
        self.max_display = max_display

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


class SessionSection(DashboardSection):
    name = "session"

    def render(self, agent, **ctx) -> str:
        s = agent.session
        title = s.title or f"会话 {s.id}"
        msgs = len(s.messages)
        if msgs:
            return f"会话: [bold]{title}[/bold] [dim]({msgs} 条消息)[/dim]"
        return "会话: [dim]新会话[/dim]"


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
    from merco.core.config import MercoConfig
    from merco.core.agent import Agent
    import merco
    from merco.tools import discover_tools, tool_registry
    discover_tools()

    if debug:
        logging.basicConfig(
            level=logging.WARNING,  # 全局默认 WARNING，不污染第三方库
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%H:%M:%S",
        )
        logging.getLogger("merco").setLevel(logging.DEBUG)
        console.print("[yellow]🔍 调试模式已开启[/yellow]")
    else:
        logging.basicConfig(level=logging.WARNING)

    cfg = MercoConfig.load(config_path)
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
                "[yellow]未配置 API Key。[/yellow]\n\n"
                "首次使用？运行 [bold]merco setup[/bold] 交互式配置，一分钟搞定。\n\n"
                "也可以手动——选一种就行：\n"
                "  [bold]• OpenAI：[/bold] export [dim]OPENAI_API_KEY=sk-...[/dim] 然后 [dim]merco run[/dim]\n"
                "  [bold]• 其他平台：[/bold] [dim]merco.json[/dim] 写 [dim]\"model\": {\"provider\": \"deepseek\", \"api_key\": \"sk-...\"}[/dim]\n"
                "  [bold]• 临时启动：[/bold] [dim]merco run -k sk-...[/dim]",
                title="⚙️ 需要配置",
                border_style="yellow",
            ))
            resp = input("\n现在配置？按 Enter 进入向导，输入 n 退出: ").strip().lower()
            if resp != "n":
                from merco.setup import run_setup_wizard
                run_setup_wizard()
                # 重新加载配置
                cfg = MercoConfig.load(config_path)
                if not cfg.model.api_key:
                    console.print("[yellow]配置未完成，退出[/yellow]")
                    raise typer.Exit(1)
            else:
                raise typer.Exit(1)

    # tools auto-registered via discover_tools()

    # ── 技能注册 ──
    from merco.skills.registry import SkillRegistry
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
    config_source = "默认值"
    for candidate in ["./merco.json", "./.merco/merco.json",
                       os.path.expanduser("~/.config/merco/config.json")]:
        if os.path.exists(candidate):
            config_source = candidate
            break

    dashboard = (Dashboard()
        .use(WelcomeSection())
        .use(SessionSection())
        .use(ModelSection())
        .use(ToolsSection(max_display=5))
        .use(SkillsSection(max_display=3))
        .use(ConfigSection())
        .use(HintSection()))

    return agent, dashboard, config_source


# ── 输入区 PromptDecorator ─────────────────────────────────────

class PromptDecorator(ABC):
    """输入区装饰器基类。新增：继承 + 实现 render() + prompt_area.use()"""
    name: str = ""

    def render(self, agent) -> str | None:
        """返回输入上方的展示文本，None 跳过"""
        return None

    def get_prompt(self) -> str:
        """返回输入提示符"""
        return "> "


class ContextBar(PromptDecorator):
    """上下文用量进度条 — 半高薄款"""
    name = "context_bar"
    _W = 16

    def __init__(self):
        self._extras: list[str] = []  # 扩展点：追加任意状态信息

    def extra(self, text: str) -> "ContextBar":
        """追加一段状态信息（模型名、模式等）"""
        self._extras.append(text)
        return self

    def render(self, agent) -> str:
        stats = agent.get_context_stats()
        thresh_p = int(stats["threshold"] * self._W)
        filled_n = int(stats["ratio"] * self._W)
        bar = "▐"
        for i in range(self._W):
            if i == thresh_p:
                bar += "│"
            elif i < filled_n:
                bar += "█"
            else:
                bar += "░"
        bar += "▌"

        color = "dim"
        if stats["ratio"] > stats["threshold"]:
            color = "yellow"
        if stats["ratio"] > 0.95:
            color = "red"

        cur, mx = stats["current"], stats["max"]

        # left: 进度条 + token 数（bar 本身已含 ▐▌）
        left = f"  [{color}]{bar}[/{color}]  [dim]{_fmt(cur)}/{_fmt(mx)}[/dim]"

        # 当前会话标题
        session_title = agent.session.title or f"会话 {agent.session.id}"
        session = f"[bold]{session_title}[/bold]"

        # right: 扩展信息 + 默认显示模型 & 模式
        default_info = f"[dim]{agent.config.model.model}[/dim]  [dim]{agent.config.sandbox_mode}[/dim]"
        extra = "  ".join(self._extras)
        if extra:
            default_info = extra + "  " + default_info

        return f"{session}  {left}  {default_info}"

    def get_prompt(self) -> str:
        return "▸ "


def _fmt(n: int) -> str:
    if n < 1000:
        return str(n)
    return f"{n / 1024:.1f}K"


class PromptArea:
    """输入区渲染器。按 use() 顺序渲染各装饰器，Panel 包裹输出。"""
    def __init__(self):
        self._decorators: list[PromptDecorator] = []

    def use(self, d: PromptDecorator) -> "PromptArea":
        self._decorators.append(d)
        return self

    def render(self, agent) -> tuple[str, str]:
        pre_parts = []
        prompt = "> "
        for d in self._decorators:
            try:
                line = d.render(agent)
                if line:
                    pre_parts.append(line)
                prompt = d.get_prompt()
            except Exception:
                pre_parts.append(f"[dim]({d.name}: render failed)[/dim]")
        return "\n".join(pre_parts), prompt



# ── REPL 交互循环 ────────────────────────────────────────────────────────

def run_repl(agent, dashboard=None, config_source=""):
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

    def _save_on_exit():
        agent.observer.save()
        agent.session.metadata["observer"] = agent.observer.snapshot()
        agent.session.save()
        agent._session_store.save_metadata(agent.session.id, agent.session.metadata)

    _on_exit(_save_on_exit)

    import cli.commands  # triggers all @cmd_registry.register decorators
    from cli.input_driver import PromptToolkitInput, InputInterrupt
    driver = PromptToolkitInput([c.name for c in cmd_registry.get_all()])



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

        # Pre-load MCP servers before first user input
        if agent.mcp_manager and agent.config.mcp_servers:
            await agent.mcp_manager.load_config(agent.config.mcp_servers)

        # Render dashboard after MCP loaded
        if dashboard:
            dashboard_text = dashboard.render(agent, config_source=config_source)
            console.print(Panel(
                dashboard_text,
                title="🚀 Mercury Code",
            ))

        try:
            while True:
                try:
                    prompt_area = (PromptArea()
                        .use(ContextBar()))
                    pre_text, prompt = prompt_area.render(agent)
                    console.print(pre_text)
                    user_input = (await driver.get_input(prompt)).strip()
                    exit_count = 0  # 正常输入，重置计数

                    # Re-register signal handlers (prompt_toolkit may have cleared them)
                    for sig in (signal.SIGINT, signal.SIGTERM):
                        try:
                            loop.remove_signal_handler(sig)
                        except (NotImplementedError, RuntimeError):
                            pass
                        loop.add_signal_handler(sig, handle_interrupt)

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

                except InputInterrupt:
                    # Ctrl+C with empty buffer → exit logic
                    exit_count += 1
                    if exit_count == 1:
                        console.print("\n[yellow]再按 Ctrl+C 退出，或输入 /exit。[/yellow]")
                    else:
                        console.print("\n[dim]再见！[/dim]")
                        break
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
    agent, dashboard, config_source = _setup_agent(config, model, api_key, debug)
    run_repl(agent, dashboard, config_source)


# ── 子命令 ────────────────────────────────────────────────────────────────

@app.command("run")
def run_cmd(
    config: str = typer.Option(None, "--config", "-c", help="配置文件路径"),
    model: str = typer.Option(None, "--model", "-m", help="指定模型"),
    api_key: str = typer.Option(None, "--api-key", "-k", help="API Key"),
    debug: bool = typer.Option(False, "--debug", "-d", help="开启调试日志"),
):
    agent, dashboard, config_source = _setup_agent(config, model, api_key, debug)
    run_repl(agent, dashboard, config_source)


@app.command("init")
def init_cmd(path: str = typer.Argument(".", help="项目路径")):
    from pathlib import Path
    from merco.core.config import MercoConfig

    config_path = Path(path) / "merco.json"
    if config_path.exists():
        console.print(f"[yellow]配置已存在: {config_path}[/yellow]")
        return

    cfg = MercoConfig()
    cfg.save(str(config_path))
    console.print(f"[green]已创建配置: {config_path}[/green]")


@app.command("skills")
def skills_cmd(
    list: bool = typer.Option(False, "--list", "-l", help="列出已加载技能"),
    path: str = typer.Option(None, "--path", "-p", help="技能目录路径"),
):
    from merco.skills.loader import SkillLoader
    from merco.skills.registry import SkillRegistry

    if list:
        registry = SkillRegistry()
        if path:
            registry.load_from_paths([path])
        else:
            registry.load_from_paths(["./.merco/skills", "~/.config/merco/skills"])

        skills = registry.list_skills()
        if skills:
            console.print(f"[bold]已加载 {len(skills)} 个技能:[/bold]")
            for skill in skills:
                console.print(f"  - {skill['name']}: {skill['description']}")
        else:
            console.print("未加载任何技能")


@app.command("setup")
def setup_cmd():
    """交互式配置 API — 引导选择平台、填写 Key 和模型"""
    from merco.setup import run_setup_wizard
    run_setup_wizard()


# ── 命令处理 ──────────────────────────────────────────────────────────────

async def handle_command(cmd: str, agent) -> bool:
    parts = cmd.split(maxsplit=1)
    name = parts[0].lower()
    args = parts[1] if len(parts) > 1 else ""

    cmd_def = cmd_registry.get(name)
    if cmd_def is None:
        console.print(f"[dim]未知命令: {name}，输入 /help 查看帮助[/dim]")
        return True

    return await cmd_def.handler(agent, args)


if __name__ == "__main__":
    app()
