"""CLI 命令定义 — 所有 REPL 命令从 handle_command() 迁移至此"""

import asyncio
from rich.console import Console
from rich.panel import Panel
from cli.registry import cmd_registry
from cli.main import ContextBar

console = Console()


# ═══════════════════════════════════════════════════════════════════
# INFO GROUP
# ═══════════════════════════════════════════════════════════════════

@cmd_registry.register("/help", "显示帮助", group="info")
async def cmd_help(agent, args):
    console.print(Panel(cmd_registry.get_help_text(), title="帮助"))
    return True


@cmd_registry.register("/model", "显示当前模型", group="info")
async def cmd_model(agent, args):
    console.print(f"当前模型: {agent.config.model.provider}/{agent.config.model.model}")
    return True


@cmd_registry.register("/context", "上下文用量", group="info")
async def cmd_context(agent, args):
    stats = agent.get_context_stats()
    bar = ContextBar()
    console.print(bar.render(agent))
    console.print(f"  阈值: {int(stats['threshold']*100)}%  |  模型推算: {'是' if stats['is_estimate'] else '否（API 实测）'}")
    return True


@cmd_registry.register("/tools", description="列出可用工具", group="info")
async def cmd_tools(agent, args):
    tools = [t for t in agent.tool_registry.list_tools() if t.check()] if agent.tool_registry else []
    if not tools:
        console.print("无可用工具")
        return True

    # Group by toolset: MCP tools use their mcp: prefix, everything else is "builtin"
    groups: dict[str, list] = {}
    for t in tools:
        if t.toolset and t.toolset.startswith("mcp:"):
            key = t.toolset
        else:
            key = "builtin"
        groups.setdefault(key, []).append(t)

    console.print("[bold]可用工具:[/bold]")
    for toolset, group_tools in sorted(groups.items()):
        if toolset.startswith("mcp:"):
            label = f"mcp:{toolset[4:]}"  # plain text, Rich brackets only for known tags
        else:
            label = "[内置]"
        console.print(f"\n  [bold yellow]{label}[/bold yellow]")
        for t in group_tools:
            raw = (t.description or "").replace("\n", " ")
            desc = raw[:57] + "..." if len(raw) > 60 else raw
            console.print(f"    [bold]{t.name}[/bold]  [dim]{desc}[/dim]")
    return True


@cmd_registry.register("/report", "会话统计报告", group="info")
async def cmd_report(agent, args):
    if args == "reset":
        agent.observer.reset()
        console.print("[dim]统计数据已清零[/dim]")
    else:
        console.print(Panel(agent.observer.report(), title="📊 Session Report"))
    return True


@cmd_registry.register("/reload-mcp", description="重新加载 MCP 服务器", group="info")
async def cmd_reload_mcp(agent, args):
    if not hasattr(agent, 'mcp_manager'):
        console.print("[dim]MCP 尚未初始化[/dim]")
        return True
    await agent.mcp_manager.reload()
    status = agent.mcp_manager.status()
    console.print(f"[green]MCP 已重载: {len(status)} 个服务器[/green]")
    for name, s in status.items():
        console.print(f"  🟢 {name}: {s['tools_count']} tools")
    return True


@cmd_registry.register("/mcp-status", description="MCP 服务器状态", group="info")
async def cmd_mcp_status(agent, args):
    if not hasattr(agent, 'mcp_manager'):
        console.print("[dim]MCP 尚未初始化[/dim]")
        return True
    status = agent.mcp_manager.status()
    if not status:
        console.print("[dim]无已连接的 MCP 服务器[/dim]")
        return True
    console.print("[bold]MCP 服务器状态:[/bold]")
    for name, s in status.items():
        icon = "🟢" if s["connected"] else "🔴"
        console.print(f"  {icon} {name}: {s['tools_count']} tools")
    return True


# ═══════════════════════════════════════════════════════════════════
# SESSION GROUP
# ═══════════════════════════════════════════════════════════════════

@cmd_registry.register("/new", "新会话", group="session")
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


@cmd_registry.register("/sessions", "历史会话列表", group="session",
                       sub={"<n>": "切换到第 n 个会话"})
async def cmd_sessions(agent, args):
    if args:
        # 切换会话：支持序号 (1,2,3) 或 session id
        sessions = agent._session_store.list_sessions(limit=20)
        target_id = None

        if args.isdigit():
            idx = int(args) - 1
            if 0 <= idx < len(sessions):
                target_id = sessions[idx]["id"]
        else:
            target_id = args  # 直接传 session id

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


@cmd_registry.register("/fork", "从当前会话创建分支", group="session")
async def cmd_fork(agent, args):
    title = args.strip() if args else ""
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
    agent.observer.reset(full=agent.config.fork_reset_observer)
    agent._restore_context()
    from merco.sandbox import snapshot
    snapshot.set_current_session(agent.session.id)
    display = new_session.title or new_session.id[:8]
    console.print(f"[green]已 fork 到: {display}[/green]")
    return True


@cmd_registry.register("/tree", "查看会话分支树", group="session")
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


@cmd_registry.register("/history", "查看当前会话完整消息记录 (支持分页)", group="session")
async def cmd_history(agent, args):
    # 分页：/history 或 /history <offset> <limit>
    try:
        argv = [int(x) for x in args.split()]
    except ValueError:
        argv = []
    offset = max(1, argv[0]) if len(argv) >= 1 else 1
    limit = min(50, argv[1]) if len(argv) >= 2 else 20

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


@cmd_registry.register("/revert", "撤销本会话的文件修改", group="session")
async def cmd_revert(agent, args):
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


# ═══════════════════════════════════════════════════════════════════
# SEARCH GROUP
# ═══════════════════════════════════════════════════════════════════

@cmd_registry.register("/search", "搜索历史消息", group="search")
async def cmd_search(agent, args):
    query = args
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


@cmd_registry.register("/recall", "从历史会话中搜索相关内容", group="search")
async def cmd_recall(agent, args):
    query = args
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


# ═══════════════════════════════════════════════════════════════════
# CONTROL GROUP
# ═══════════════════════════════════════════════════════════════════

@cmd_registry.register("/exit", "退出", group="control")
@cmd_registry.register("/quit", "退出", group="control")
@cmd_registry.register("/q", "退出", group="control")
async def cmd_exit(agent, args):
    console.print("[dim]再见！[/dim]")
    return False
