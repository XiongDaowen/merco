"""用户审批对话框 — 展示 diff 并等待确认，支持 unified / split 两种视图"""

import asyncio
import difflib
import logging
import shutil
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text
from merco.core.config import MercoConfig

console = Console()
logger = logging.getLogger("merco.sandbox")

_SPLIT_MIN_WIDTH = 80


def _term_width() -> int:
    try:
        return shutil.get_terminal_size().columns
    except Exception:
        return 80


def _read_config() -> str:
    try:
        cfg = MercoConfig.load()
        return cfg.sandbox_mode
    except Exception:
        return "ask"


def _render_unified(diff_text: str, title: str) -> Panel:
    """行内对照（unified diff）"""
    syntax = Syntax(diff_text, "diff", theme="monokai",
                    line_numbers=False, word_wrap=True)
    return Panel(syntax, title=title, border_style="yellow",
                 subtitle="行内对照（- 删除  + 添加）")


_CONTEXT = 3  # 变更块前后保留的上下文行数


def _render_split(old_content: str, new_content: str, title: str, filepath: str) -> None:
    """左右对照 diff — SequenceMatcher 对齐 + 上下文裁剪 + 仅染色变更行"""
    width = _term_width()
    # 行号(5) + 分隔符(3) + 行号(5) = 13 字符留给 chrome
    gutter = 13
    half = max(25, (width - gutter) // 2)

    old_lines = old_content.splitlines()
    new_lines = new_content.splitlines()

    sm = difflib.SequenceMatcher(None, old_lines, new_lines)
    opcodes = sm.get_opcodes()

    # ── 阶段 1：构建 (old_ln, old_text, new_ln, new_text, change_type) 行 ──
    rows: list[tuple[str, str, str, str, str]] = []

    for i, (tag, i1, i2, j1, j2) in enumerate(opcodes):
        if tag == "equal":
            n = i2 - i1
            has_prev_change = i > 0 and opcodes[i - 1][0] != "equal"
            has_next_change = i < len(opcodes) - 1 and opcodes[i + 1][0] != "equal"

            if has_prev_change and has_next_change:
                # 夹在两个变更块之间
                if n <= 2 * _CONTEXT + 1:
                    for k in range(n):
                        rows.append((str(i1 + k + 1), old_lines[i1 + k],
                                     str(j1 + k + 1), new_lines[j1 + k], "equal"))
                else:
                    for k in range(_CONTEXT):
                        rows.append((str(i1 + k + 1), old_lines[i1 + k],
                                     str(j1 + k + 1), new_lines[j1 + k], "equal"))
                    rows.append(("", "···", "", "···", "gap"))
                    for k in range(n - _CONTEXT, n):
                        rows.append((str(i1 + k + 1), old_lines[i1 + k],
                                     str(j1 + k + 1), new_lines[j1 + k], "equal"))
            elif has_prev_change:
                show_n = min(n, _CONTEXT + 1)
                for k in range(show_n):
                    rows.append((str(i1 + k + 1), old_lines[i1 + k],
                                 str(j1 + k + 1), new_lines[j1 + k], "equal"))
                if n > show_n:
                    rows.append(("", "···", "", "···", "gap"))
            elif has_next_change:
                show_n = min(n, _CONTEXT + 1)
                if n > show_n:
                    rows.append(("", "···", "", "···", "gap"))
                for k in range(n - show_n, n):
                    rows.append((str(i1 + k + 1), old_lines[i1 + k],
                                 str(j1 + k + 1), new_lines[j1 + k], "equal"))
            # 孤立的 equal 块（无相邻变更）→ 跳过
        elif tag == "replace":
            for k in range(max(i2 - i1, j2 - j1)):
                old_idx = i1 + k
                new_idx = j1 + k
                old_ln = str(old_idx + 1) if old_idx < i2 else ""
                old_t = old_lines[old_idx] if old_idx < i2 else ""
                new_ln = str(new_idx + 1) if new_idx < j2 else ""
                new_t = new_lines[new_idx] if new_idx < j2 else ""
                rows.append((old_ln, old_t, new_ln, new_t, "replace"))
        elif tag == "delete":
            for k in range(i1, i2):
                rows.append((str(k + 1), old_lines[k], "", "", "delete"))
        elif tag == "insert":
            for k in range(j1, j2):
                rows.append(("", "", str(k + 1), new_lines[k], "insert"))

    # 去掉首尾的 gap
    while rows and rows[0][4] == "gap":
        rows.pop(0)
    while rows and rows[-1][4] == "gap":
        rows.pop(-1)

    if not rows:
        console.print(f"[bold yellow]{title}[/bold yellow]")
        console.print("[dim](无差异)[/dim]")
        return

    # ── 阶段 2：渲染 Rich Table ──
    table = Table(show_header=False, box=None, padding=(0, 1),
                  show_edge=False, expand=False, highlight=False)
    table.add_column(width=5, justify="right")   # 旧行号
    table.add_column(width=half, no_wrap=True)    # 旧内容
    table.add_column(width=1, justify="center")   # │
    table.add_column(width=5, justify="right")   # 新行号
    table.add_column(width=half, no_wrap=True)    # 新内容

    for old_ln, old_text, new_ln, new_text, change_type in rows:
        old_t = _trunc(old_text, half)
        new_t = _trunc(new_text, half)

        if change_type == "gap":
            table.add_row("", "···", "", "", "···")
        elif change_type == "equal":
            table.add_row(
                Text(old_ln, style="dim"),
                Text(old_t, style="dim"),
                Text("│", style="dim"),
                Text(new_ln, style="dim"),
                Text(new_t, style="dim"),
            )
        elif change_type == "delete":
            table.add_row(
                Text(old_ln, style="bold red"),
                Text(old_t, style="red"),
                Text("│", style="dim"),
                "",
                "",
            )
        elif change_type == "insert":
            table.add_row(
                "", "",
                Text("│", style="dim"),
                Text(new_ln, style="bold green"),
                Text(new_t, style="green"),
            )
        elif change_type == "replace":
            table.add_row(
                Text(old_ln, style="bold red") if old_ln else "",
                Text(old_t, style="red") if old_t else "",
                Text("│", style="dim"),
                Text(new_ln, style="bold green") if new_ln else "",
                Text(new_t, style="green") if new_t else "",
            )

    console.print(f"[bold yellow]{title}[/bold yellow]")
    console.print(table)


def _trunc(s: str, width: int) -> str:
    """截断到 width 宽度，超长加 …"""
    if len(s) <= width:
        return s
    return s[:width - 1] + "\u2026"


async def confirm_edit(
    diff_text: str,
    path: str,
    edits_count: int = 1,
    old_content: str | None = None,
    new_content: str | None = None,
    view: str = "unified",
) -> bool:
    """展示 diff 并等待用户确认修改

    Args:
        diff_text: unified diff 文本
        path: 文件路径
        edits_count: 编辑块数量
        old_content: 旧内容（split view 需要）
        new_content: 新内容（split view 需要）
        view: 显示模式 — "unified"（行内对照）或 "split"（左右对照）

    Returns:
        True=确认, False=取消
    """
    sandbox_mode = _read_config()
    if sandbox_mode == "auto":
        return True  # 完全静默
    if not diff_text.strip():
        return True

    title: str = "\U0001f4dd 修改预览"
    if edits_count > 1:
        title += f"（{edits_count} 处改动）"

    want_split = view == "split" and old_content is not None and new_content is not None
    if want_split and _term_width() < _SPLIT_MIN_WIDTH:
        title += f" [dim](终端 {_term_width()}列, 降级为行内对照)[/dim]"
        want_split = False

    # ── 展示 diff（ask / show 都展示）──
    if want_split:
        _render_split(old_content, new_content, title, path)
    else:
        console.print(_render_unified(diff_text, title))

    console.print(Rule(style="dim"))

    try:
        if sandbox_mode == "show":
            console.print("[dim]  ✓ 自动应用修改[/dim]")
            return True
        elif sandbox_mode == "ask":
            console.print("[bold yellow]确认修改？[/bold yellow] "
                          "[dim]按 y 确认 / 其他任意键取消 [/dim]", end="")
            resp = await asyncio.to_thread(input, "")
            return resp.strip().lower() in ("y", "yes")
        else:
            logger.warning("未知 sandbox_mode=%s, 默认拒绝", sandbox_mode)
            return False
    except KeyboardInterrupt:
        return False  # 拒绝编辑
