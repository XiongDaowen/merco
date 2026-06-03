# Slash 命令候选面板 — 实现计划

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Tab 补全 + Rich 弹出面板 + CommandRegistry 可拓展注册表 + 迁移现有命令。

**Architecture:** CommandRegistry（数据源）→ readline completer（Tab 补全）+ Rich Panel（弹出展示）→ handle_command 简化为单行调用。

**Tech Stack:** Python 3.12+, readline, rich, typer

---

### Task 1: cli/registry.py — CommandRegistry 核心

**Objective:** 新建 CommandDef dataclass + CommandRegistry 类（register/match/get_all/get/get_help_text）。

**Files:**
- Create: `cli/registry.py`
- Create: `tests/cli/test_registry.py`

**Step 1: 写测试**

```python
# tests/cli/test_registry.py
import pytest
from cli.registry import CommandRegistry, cmd_registry

class TestCommandRegistry:
    def test_register_and_get(self):
        reg = CommandRegistry()
        async def handler(agent, args): return True
        reg.register("/test", "test command", handler, group="test")
        cmd = reg.get("/test")
        assert cmd.name == "/test"
        assert cmd.description == "test command"

    def test_match_prefix(self):
        reg = CommandRegistry()
        reg.register("/fork", "fork", _noop, group="session")
        reg.register("/foo", "foo", _noop, group="test")
        matches = reg.match("/f")
        assert len(matches) == 2
        names = {m.name for m in matches}
        assert "/fork" in names and "/foo" in names

    def test_match_exact(self):
        reg = CommandRegistry()
        reg.register("/fork", "fork", _noop, group="session")
        matches = reg.match("/fork")
        assert len(matches) == 1
        assert matches[0].name == "/fork"

    def test_get_all_grouped(self):
        reg = CommandRegistry()
        reg.register("/a", "a", _noop, group="info")
        reg.register("/b", "b", _noop, group="session")
        all_cmds = reg.get_all()
        assert len(all_cmds) == 2
        info_cmds = reg.get_all("info")
        assert len(info_cmds) == 1

    def test_sub_commands(self):
        reg = CommandRegistry()
        reg.register("/sessions", "manage", _noop, 
                     sub={"list": "列出", "<n>": "切换"}, group="session")
        cmd = reg.get("/sessions")
        assert cmd.sub_commands["list"] == "列出"

    def test_get_help_text(self):
        reg = CommandRegistry()
        reg.register("/fork", "fork session", _noop, group="session")
        text = reg.get_help_text()
        assert "/fork" in text
        assert "fork session" in text

async def _noop(agent, args): return True
```

**Step 2: 运行测试（FAIL）**

```bash
uv run pytest tests/cli/test_registry.py -v
```

**Step 3: 写实现 — `cli/registry.py`**

```python
"""命令注册表 — 可拓展、UI 无关的命令定义与查询"""

from dataclasses import dataclass, field
from typing import Callable


@dataclass
class CommandDef:
    name: str
    description: str
    handler: Callable
    sub_commands: dict[str, str] = field(default_factory=dict)
    group: str = "general"


class CommandRegistry:
    def __init__(self):
        self._commands: dict[str, CommandDef] = {}

    def register(self, name: str, description: str, handler=None, *,
                 sub: dict[str, str] | None = None,
                 group: str = "general"):
        """注册命令。可做装饰器用。"""
        def decorator(fn):
            self._commands[name] = CommandDef(
                name=name, description=description, handler=fn,
                sub_commands=sub or {}, group=group,
            )
            return fn

        if handler is not None:
            # 直接调用模式
            return decorator(handler)
        return decorator

    def match(self, prefix: str) -> list[CommandDef]:
        """前缀匹配，返回候选命令。按名称排序。"""
        prefix = prefix.lower()
        return sorted(
            [c for c in self._commands.values() if c.name.lower().startswith(prefix)],
            key=lambda c: c.name,
        )

    def get_all(self, group: str | None = None) -> list[CommandDef]:
        """全部命令或按分组筛选。"""
        cmds = list(self._commands.values())
        if group:
            cmds = [c for c in cmds if c.group == group]
        return sorted(cmds, key=lambda c: c.name)

    def get(self, name: str) -> CommandDef | None:
        """精确查找。"""
        return self._commands.get(name.lower())

    def get_help_text(self) -> str:
        """生成 /help 展示文本。"""
        groups: dict[str, list[str]] = {}
        for cmd in sorted(self._commands.values(), key=lambda c: c.name):
            groups.setdefault(cmd.group, []).append(
                f"{cmd.name:14s} - {cmd.description}"
            )
        lines = ["[bold]可用命令[/bold]\n"]
        for grp, entries in groups.items():
            lines.append(f"[bold]{grp}[/bold]")
            lines.extend(f"  {e}" for e in entries)
            lines.append("")
        return "\n".join(lines)

    def __len__(self):
        return len(self._commands)


# 模块级全局单例
cmd_registry = CommandRegistry()
```

**Step 4: 运行测试（PASS）**

```bash
uv run pytest tests/cli/test_registry.py -v
```

**Step 5: Commit**

```bash
git add cli/registry.py tests/cli/test_registry.py
git commit -m "feat: CommandRegistry with register/match/get_all/get_help_text"
```

---

### Task 2: cli/commands.py — 迁移所有现有命令

**Objective:** 把 `cli/main.py` 中 `handle_command()` 的全部 15 个命令迁移到 `cli/commands.py`，用装饰器注册。

**Files:**
- Create: `cli/commands.py`
- Modify: `cli/main.py`（删除 if/elif 链中的 handler 逻辑，后续 Task 3 简化）

**Step 1: 写 `cli/commands.py`**

把所有现有命令从 `handle_command` 里搬出来，改成独立 async 函数 + 装饰器：

```python
"""CLI 命令定义 — 所有命令在此注册"""
from cli.registry import cmd_registry
from rich.console import Console
from rich.panel import Panel

console = Console()

# ── info 组 ────────────────────────────

@cmd_registry.register("/help", desc="显示帮助", group="info")
async def cmd_help(agent, args):
    console.print(Panel(cmd_registry.get_help_text(), title="帮助"))
    return True

@cmd_registry.register("/model", desc="显示当前模型", group="info")
async def cmd_model(agent, args):
    console.print(f"当前模型: {agent.config.model.provider}/{agent.config.model.model}")
    return True

@cmd_registry.register("/context", desc="上下文用量", group="info")
async def cmd_context(agent, args):
    from cli.main import ContextBar
    stats = agent.get_context_stats()
    bar = ContextBar()
    console.print(bar.render(agent))
    console.print(f"  阈值: {int(stats['threshold']*100)}%  |  "
                  f"模型推算: {'是' if stats['is_estimate'] else '否（API 实测）'}")
    return True

@cmd_registry.register("/tools", desc="列出可用工具", group="info")
async def cmd_tools(agent, args):
    tools = agent.tool_registry.list_tools() if agent.tool_registry else []
    if tools:
        console.print("[bold]可用工具:[/bold]")
        for tool in tools:
            console.print(f"  - {tool.name}: {tool.description}")
    else:
        console.print("无可用工具")
    return True

@cmd_registry.register("/report", desc="会话统计报告", group="info")
async def cmd_report(agent, args):
    if args.strip() == "reset":
        agent.observer.reset()
        console.print("[dim]统计数据已清零[/dim]")
    else:
        console.print(Panel(agent.observer.report(), title="📊 Session Report"))
    return True

# ── session 组 ──────────────────────────

@cmd_registry.register("/new", desc="新建会话", group="session")
async def cmd_new(agent, args):
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

@cmd_registry.register("/sessions", desc="历史会话列表与切换", group="session",
                        sub={"<n>": "切换到第 n 个会话"})
async def cmd_sessions(agent, args):
    arg = args.strip()
    if arg:
        sessions = agent._session_store.list_sessions(limit=20)
        target_id = None
        if arg.isdigit():
            idx = int(arg) - 1
            if 0 <= idx < len(sessions):
                target_id = sessions[idx]["id"]
        else:
            target_id = arg
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

@cmd_registry.register("/fork", desc="从当前会话创建分支", group="session")
async def cmd_fork(agent, args):
    title = args.strip() if args else ""
    agent.observer.save()
    agent.session.metadata["observer"] = agent.observer.snapshot()
    agent.session.save()
    agent._session_store.save_metadata(agent.session.id, agent.session.metadata)
    from merco.core.session import Session
    new_session = Session.fork(agent.session.id, agent._session_store, title=title or None)
    if not new_session:
        console.print("[red]Fork 失败[/red]")
        return True
    agent.session = new_session
    agent.observer.reset(full=agent.config.fork_reset_observer)
    agent._restore_context()
    from merco.sandbox import snapshot
    snapshot.set_current_session(agent.session.id)
    display = new_session.title or new_session.id[:8]
    console.print(f"[green]已 fork 到: {display}[/green]")
    return True

@cmd_registry.register("/tree", desc="查看会话分支树", group="session")
async def cmd_tree(agent, args):
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

@cmd_registry.register("/history", desc="查看当前会话完整消息记录 (支持分页)", group="session")
async def cmd_history(agent, args):
    arg = args.strip()
    try:
        nums = [int(x) for x in arg.split()]
    except ValueError:
        nums = []
    offset = max(1, nums[0]) if len(nums) >= 1 else 1
    limit = min(50, nums[1]) if len(nums) >= 2 else 20
    session_data = agent._session_store.load_session(agent.session.id)
    msgs = session_data.get("messages", []) if session_data else []
    if not msgs:
        console.print("[dim]当前会话无消息[/dim]")
        return True
    total = len(msgs)
    page = msgs[offset-1:offset-1+limit]
    end_idx = min(offset+limit-1, total)
    console.print(f"[bold]📋 {agent.session.title or agent.session.id[:8]}"
                  f" ({offset}-{end_idx}/{total}):[/bold]")
    for i, m in enumerate(page, offset):
        role_icon = {"user": "👤", "assistant": "🤖", "tool": "🔧", "system": "⚙️"}.get(m["role"], "❓")
        content = (m.get("content") or "")[:120].replace("\n", " ")
        timestamp = m.get("timestamp", "")[:16]
        console.print(f"  {i:3d}. {role_icon} [dim]{timestamp}[/dim] {content}")
    if end_idx < total:
        console.print(f"  [dim]... 共 {total} 条。下一页: /history {offset+limit}[/dim]")
    return True

# ── search 组 ──────────────────────────

@cmd_registry.register("/search", desc="搜索历史消息", group="search")
async def cmd_search(agent, args):
    query = args.strip()
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

@cmd_registry.register("/recall", desc="从历史会话中搜索相关内容", group="search")
async def cmd_recall(agent, args):
    query = args.strip()
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

# ── control 组 ─────────────────────────

@cmd_registry.register("/exit", desc="退出", group="control")
@cmd_registry.register("/quit", desc="退出", group="control")
@cmd_registry.register("/q", desc="退出", group="control")
async def cmd_exit(agent, args):
    return False  # False = 退出 REPL
```

**Step 2: 验证语法 + 无 import 冲突**

```bash
uv run python -c "import cli.commands; print(f'{len(cli.commands.cmd_registry)} commands loaded')"
```

Expected: `15 commands loaded`

**Step 3: Commit**

```bash
git add cli/commands.py
git commit -m "feat: migrate all CLI commands to CommandRegistry"
```

---

### Task 3: cli/main.py — readline completer + 简化 handle_command

**Objective:** 加 readline Tab 补全 + Rich 弹出面板 + 简化 handle_command 为注册表调用。删除旧的 if/elif 链。

**Files:**
- Modify: `cli/main.py`

**Step 1: 在 `run_repl()` 开头绑定 readline completer**

```python
# 在 run_repl() 函数内，loop 前：
from cli.registry import cmd_registry
import cli.commands  # 触发命令注册

def _setup_completer():
    _shown_panel = False

    def completer(text, state):
        nonlocal _shown_panel
        # 弹出面板：第一次遇到 "/" 时
        if text == "/" and state == 0 and not _shown_panel:
            _shown_panel = True
            _render_command_panel()

        matches = cmd_registry.match(text)
        if text == "/":
            # "/" 匹配全部，只返回精确匹配的，不堆砌
            return None
        if state < len(matches):
            return matches[state].name
        return None

    readline.set_completer(completer)
    readline.parse_and_bind("tab: complete")
    readline.set_completer_delims(" \t\n")

def _render_command_panel():
    groups = {}
    for cmd in cmd_registry.get_all():
        groups.setdefault(cmd.group, []).append(cmd)
    
    lines = []
    for grp, cmds in groups.items():
        lines.append(f"[bold yellow]{grp}[/bold yellow]")
        for c in cmds:
            sub_hint = ""
            if c.sub_commands:
                sub_keys = " | ".join(c.sub_commands.keys())
                sub_hint = f"  [dim]→ {sub_keys}[/dim]"
            lines.append(f"  [bold]{c.name:14s}[/bold] [dim]{c.description}[/dim]{sub_hint}")
        lines.append("")
    
    console.print(Panel("\n".join(lines), title="📋 可用命令", border_style="dim"))
```

**Step 2: 替换 handle_command**

原有 `handle_command` 的全部内容（~180 行 if/elif 链）替换为：

```python
async def handle_command(cmd: str, agent) -> bool:
    parts = cmd.split(maxsplit=1)
    name = parts[0].lower()
    args = parts[1] if len(parts) > 1 else ""

    cmd_def = cmd_registry.get(name)
    if cmd_def is None:
        console.print(f"[dim]未知命令: {name}，输入 /help 查看帮助[/dim]")
        return True

    return await cmd_def.handler(agent, args)
```

**Step 3: 手动验证**

```bash
# 启动 merco，测试：
# / + Tab → 弹出面板
# /hel + Tab → 补全为 /help
# /fork + Tab → 补全
# /help → 显示命令列表（从 registry 生成）
# /exit → 退出
```

**Step 4: Commit**

```bash
git add cli/main.py
git commit -m "feat: readline command completer + simplified handle_command via registry"
```

---

## Task Order

```
Task 1: CommandRegistry      ← 无依赖
Task 2: 迁移命令到 commands.py ← 依赖 Task 1
Task 3: completer + handle   ← 依赖 Task 1+2
```
