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

    console.print(Panel(
        dashboard.render(agent, config_source=config_source),
        title="🚀 Mercury Code",
    ))
    return agent


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

    def _save_on_exit():
        agent.observer.save()
        agent.session.metadata["observer"] = agent.observer.snapshot()
        agent.session.save()
        agent._session_store.save_metadata(agent.session.id, agent.session.metadata)

    _on_exit(_save_on_exit)

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
                    prompt_area = (PromptArea()
                        .use(ContextBar()))
                    pre_text, prompt = prompt_area.render(agent)
                    console.print(f"\n{pre_text}")
                    user_input = await asyncio.to_thread(input, prompt)
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
            "/sessions - 历史会话列表\n"
            "/search   - 搜索历史消息\n"
            "/recall   - 从历史会话中搜索相关内容\n"
            "/report   - 会话统计报告\n"
            "/model    - 显示当前模型\n"
            "/tools    - 列出可用工具\n"
            "/fork     - 从当前会话创建分支\n"
            "/tree     - 查看会话分支树\n"
            "/context  - 上下文用量\n"
            "/skills   - 列出已加载技能\n"
            "/history  - 查看本会话的文件修改历史\n"
            "/revert   - 撤销本会话的文件修改",
            title="帮助",
        ))
        return True

    elif command == "/new":
        agent.observer.save()
        agent.session.metadata["observer"] = agent.observer.snapshot()
        agent.session.save()
        agent._session_store.save_metadata(agent.session.id, agent.session.metadata)
        agent.reset()
        agent.observer.reset(full=True)
        from merco.sandbox import snapshot
        snapshot.set_current_session(agent.session.id)
        console.print("[dim]已开启新会话[/dim]")
        return True

    elif command == "/report":
        arg = parts[1] if len(parts) > 1 else ""
        if arg == "reset":
            agent.observer.reset()
            console.print("[dim]统计数据已清零[/dim]")
        else:
            console.print(Panel(agent.observer.report(), title="📊 Session Report"))
        return True

    elif command == "/search":
        query = parts[1] if len(parts) > 1 else ""
        if not query:
            console.print("[dim]用法: /search <关键词>[/dim]")
            return True
        from merco.memory.session_search import SessionSearch
        searcher = SessionSearch(agent._session_store)
        results = searcher.search(query, limit=10)
        if not results:
            console.print(f"[dim]未找到 '{query}' 相关结果[/dim]")
            return True
        console.print(f"[bold]🔍 '{query}' 搜索结果:[/bold]")
        for i, r in enumerate(results):
            sid = r["session_id"][:8]
            marker = " ← 当前" if r["session_id"] == agent.session.id else ""
            console.print(f"  {i+1}. [bold]{r['session_title'] or sid}[/bold]{marker}")
            console.print(f"     [dim]{r['snippet']}[/dim]")
            console.print(f"     [bright_black]{r['role'][:8]:8s}  {r['timestamp'][:16]}[/bright_black]")
        return True

    elif command == "/model":
        console.print(f"当前模型: {agent.config.model.provider}/{agent.config.model.model}")
        return True

    elif command == "/context":
        stats = agent.get_context_stats()
        bar = ContextBar()
        console.print(bar.render(agent))
        console.print(f"  阈值: {int(stats['threshold']*100)}%  |  模型推算: {'是' if stats['is_estimate'] else '否（API 实测）'}")
        return True

    elif command == "/history":
        from merco.sandbox import snapshot
        session_id = snapshot.get_current_session()
        if not session_id:
            console.print("[red]未找到当前会话[/red]")
            return True
        records = snapshot.history(session_id)
        if not records:
            console.print("[dim]当前会话无文件修改记录[/dim]")
            return True
        console.print(f"[bold]📋 会话 {session_id[:8]} 的文件修改:[/bold]")
        for i, rec in enumerate(records):
            from datetime import datetime
            ts = rec.get("timestamp", "")[:19].replace("T", " ")
            console.print(f"  {i}. [yellow]{rec['path']}[/yellow]  {ts}")
        return True

    elif command == "/revert":
        from merco.sandbox import snapshot
        session_id = snapshot.get_current_session()
        if not session_id:
            console.print("[red]未找到当前会话[/red]")
            return True
        records = snapshot.history(session_id)
        if not records:
            console.print("[dim]当前会话无文件修改记录[/dim]")
            return True
        resp = await asyncio.to_thread(
            input, f"将撤销 {len(records)} 处修改，确认？[y/N] ")
        if resp.strip().lower() not in ("y", "yes"):
            console.print("[dim]已取消[/dim]")
            return True
        results = snapshot.revert(session_id)
        ok = sum(1 for r in results if r["reverted"])
        fail = sum(1 for r in results if not r["reverted"])
        console.print(f"[green]已恢复 {ok} 个文件[/green]"
                      + (f"，{fail} 个失败" if fail else ""))
        return True

    elif command == "/sessions":
        arg = parts[1] if len(parts) > 1 else ""

        if arg:
            # 切换会话：支持序号 (1,2,3) 或 session id
            sessions = agent._session_store.list_sessions(limit=20)
            target_id = None

            if arg.isdigit():
                idx = int(arg) - 1
                if 0 <= idx < len(sessions):
                    target_id = sessions[idx]["id"]
            else:
                target_id = arg  # 直接传 session id

            if target_id and target_id != agent.session.id:
                from merco.core.session import Session
                agent.observer.save()
                agent.session.metadata["observer"] = agent.observer.snapshot()
                agent.session.save()
                agent._session_store.save_metadata(agent.session.id, agent.session.metadata)
                s = Session.load(target_id, agent._session_store)
                if s:
                    agent.session = s
                    agent.observer.reset()
                    agent._restore_context()
                    from merco.sandbox import snapshot
                    snapshot.set_current_session(agent.session.id)
                    console.print(f"[green]已切换到: {s.title or s.id}[/green]")
                else:
                    console.print(f"[red]会话 {target_id} 不存在[/red]")
            elif target_id == agent.session.id:
                console.print("[dim]已经是当前会话[/dim]")
            else:
                console.print("[red]无效的会话序号[/red]")
            return True

        # 列出
        sessions = agent._session_store.list_sessions(limit=20)
        if not sessions:
            console.print("[dim]无历史会话[/dim]")
            return True
        console.print("[bold]📋 历史会话:[/bold]")
        for i, s in enumerate(sessions):
            marker = " ← 当前" if s["id"] == agent.session.id else ""
            title = s["title"] or f"会话 {s['id']}"
            console.print(
                f"  {i+1}. [bold]{title}[/bold]{marker}"
                f"  [dim]{s['message_count']} 条消息  {s['updated_at'][:10]}"
                f"  [/dim][bright_black]{s['id']}[/bright_black]")
        console.print("[dim]用 /sessions <序号> 切换会话[/dim]")
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

    elif command == "/fork":
        title = parts[1].strip() if len(parts) > 1 else ""
        # Save current session
        agent.observer.save()
        agent.session.metadata["observer"] = agent.observer.snapshot()
        agent.session.save()
        agent._session_store.save_metadata(agent.session.id, agent.session.metadata)

        from merco.core.session import Session
        new_session = Session.fork(agent.session.id, agent._session_store,
                                    title=title or None)
        if not new_session:
            console.print("[red]Fork 失败[/red]")
            return True

        agent.session = new_session
        agent.observer.reset()
        agent._restore_context()
        from merco.sandbox import snapshot
        snapshot.set_current_session(agent.session.id)
        display = new_session.title or new_session.id[:8]
        console.print(f"[green]已 fork 到: {display}[/green]")
        return True

    elif command == "/tree":
        children = agent._session_store.get_children(agent.session.id)
        session_data = agent._session_store.load_session(agent.session.id)
        parent = session_data.get("parent_id") if session_data else None
        if not children and not parent:
            console.print("[dim]单会话，无分支[/dim]")
            return True
        if parent:
            console.print(f"[dim]父会话: {parent[:8]}[/dim]")
        if children:
            console.print("[bold]子会话:[/bold]")
            for c in children[:10]:
                console.print(f"  - {c['title'] or c['id'][:8]}  [dim]{c['created_at'][:10]}[/dim]")
        return True

    elif command == "/recall":
        query = parts[1] if len(parts) > 1 else ""
        if not query:
            console.print("[dim]用法: /recall <关键词>[/dim]")
            return True
        recalled = await agent.recaller.recall(query)
        if not recalled:
            console.print("[dim]未找到相关历史[/dim]")
        else:
            console.print(f"[bold]🔍 '{query}' 召回结果:[/bold]")
            for i, r in enumerate(recalled, 1):
                console.print(f"  {i}. [{r.session_title}] [dim]({r.source}, {r.score:.1f})[/dim]")
                console.print(f"     [bright_black]{r.snippet}[/bright_black]")
        return True

    else:
        console.print(f"[dim]未知命令: {command}，输入 /help 查看帮助[/dim]")
        return True


if __name__ == "__main__":
    app()
