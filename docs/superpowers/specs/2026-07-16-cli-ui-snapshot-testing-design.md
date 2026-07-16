# CLI UI 渲染快照测试方案

日期：2026-07-16
状态：待审核

## 问题

用户希望在 CLI 各类场景下知道真实表现，但当前测试覆盖集中在纯函数和导入：

- `tests/cli/test_main.py` 只测 `_fmt()` 这种纯格式化函数
- `tests/cli/test_cli_help.py` 用 `typer.testing.CliRunner` 验 help 输出，不验主流程 UI
- 没有测试在真实异常路径下断言渲染（如 `agent.run()` 失败时是否暴露 stacktrace、流式/非流式 Panel 行为差异、`CancelledError`/`EOFError`/键盘中断文案）
- 也不敢靠人手"看一遍"所有斜杠命令在 0 工具/MCP 未初始化/observer None 时的输出

更重要：**用户原话：「会话期间大模型调用失败的呈现，是否用户友好」** —— 这条路径靠纯单测无法覆盖。

不通过截图也能断言 UI：**用 Rich 的 `Console(file=io.StringIO(), record=True)` 捕获到文本与 Rich markup，断言文案、样式标签、Panel 内容。** 这比截图更快、更脆对立面更难，且在 CI 里 100% 可跑。

## 目标

1. 全量断言 CLI 主流程在不同状态下的**渲染快照**：dashboard 首页、斜杠命令、输入区、生命周期文案、LLM 异常路径
2. **杜绝 stacktrace 裸奔**：测试钉住「`agent.run()` 抛异常时必须显示 `[red]错误: <e>[/red]` 风格的中文友好提示，不得泄露 `Traceback ... File "..."`」
3. **流式/非流式分支都被覆盖**：stream 模式下不打 Panel vs 非 stream 模式下打 `Panel(Markdown(response))` 的差异必须可回归
4. 为 `run_repl()` 这种巨型 async 函数**抽出可测小函数** `_run_one_turn()`，副产物是降低主循环复杂度
5. 零依赖：不引入任何测试框架；pytest + `pytest-asyncio` + monkeypatch 已经够了
6. 速度可控：单测套件 `< 5s`（capture console 单测天然快）

## 非目标

- **不做 ANSI 颜色码断言**。颜色是终端主题的事，断言 markup 文本（`[red]`/`[bold]`）就够了
- **不做 panel 边框字符断言**。那是 Rich 的责任，不归我们
- **不引入截图框架**（如 pytest-textual-snapshot / asciinema）。用户明确说了不要这种
- **不重构 `run_repl()` 整体**。只抽一个 `_run_one_turn()` 函数出来
- **不改任何 UI 文案**。我们只描述现状、把现状钉住；如果发现 bug 也只是新增"现状测试"作为安全网，未来修复时再调整
- **不替换 `typer.testing.CliRunner` 已覆盖的部分**（如 `--help`）
- **不测试 web 接口的 UI**（`web/app.py` 不在本设计范围）

## 架构

### 核心机制：Rich Console 捕获

`rich.console.Console` 接受 `file` 参数和 `record=True`，使所有 `console.print()` / `console.rule()` / `console.input()` 都流到该文件对象。捕获到的对象可调用 `export_text()` / `export_text(styles=True)`，返回包含 markup 的纯文本字符串。

```python
import io
from rich.console import Console

buf = io.StringIO()
capture = Console(file=buf, force_terminal=True, width=120, record=True)
```

`cli/main.py` 第 18 行 `console = Console()` 是模块级单例；同样 `cli/commands.py` 第 9 行。测试用 `monkeypatch.setattr()` 在测试期间替换指向 capture 实例。该全局变量是设计层面允许的注入点（不破坏现有代码）。

### 抽象：第 1 层 vs 第 2 层

| 层 | 测什么 | 捕获方式 | 例 |
|---|---|---|---|
| **第 1 层：渲染器直接返回** | `DashboardSection.render()` / `PromptArea.render()` —— 这些方法只 `return "Rich markup string"`，根本不打印 | 直接读返回值 | `assert "工具" in ToolsSection().render(agent)` |
| **第 2 层：`console.print()` 输出** | `commands.py` 的所有 `cmd_*`、repl 异常路径、`run_repl()` 抽取出的 `_run_one_turn()` | monkeypatch 全局 console + capture buffer | 见下文 |

第 1 层零成本（不捕获 IO、不耗 IO），第 2 层是核心投资。

### 改动点 1：抽 `_run_one_turn()`

`cli/main.py` 当前 `run_repl()`（第 360 行附近）是个 100+ 行的 `while True` 大循环。把"接收一行输入 → 跑 agent → 处理异常"这段抽出成：

```python
async def _run_one_turn(
    agent,
    prompt_area: PromptArea,
    dashboard: Dashboard,
) -> str | None:
    """处理一轮用户输入：装饰器预渲染 → agent.run → 异常分支 → 返回 None 表示退出。"""
```

返回值语义：

- `"continue"`：本轮处理完，回到循环读下一行
- `"exit"`：用户按了退出键，REPL 退出
- `"back_to_input"`：本轮是 `/` 斜杠命令且需要继续，或 `CancelledError` 后回到读输入

抽出后只测这个函数就够了。`run_repl()` 大循环简化成 `while await _run_one_turn() != "exit":`。

测试时构造一个 `fake_agent`（`MagicMock` + `AsyncMock` 模拟 `agent.run()`），控制其返回正常/抛特定异常，断言 `console.print()` 出来的文案。

### 改动点 2：共享 fixture

新增 `tests/cli/conftest.py`：

```python
@pytest.fixture
def capture_console(monkeypatch):
    """替换 cli.main 和 cli.commands 的全局 console，捕获所有输出。

    Returns (console, buffer)。
    """
    import io
    from rich.console import Console
    from cli import main, commands

    buf = io.StringIO()
    capture = Console(file=buf, force_terminal=True, width=120, record=True)
    monkeypatch.setattr(main, "console", capture)
    monkeypatch.setattr(commands, "console", capture)
    return capture, buf
```

主项目断言时读取 `buf.getvalue()` 或 `capture.export_text(inline_styles=False)`。

### 数据流（测试侧）

```
测试代码（pytest）
  ↓ 构造 fake_agent / 真实 mock agent
  ↓ fixture 替换 console → capture buffer
  ↓ 调用被测函数（DashboardSection.render / cmd_* / _run_one_turn）
  ↓ 读取 buffer / export_text()
  ↓ 断言文本包含 / 不包含 关键文案
```

## 改动点汇总

| 文件 | 改动 |
|---|---|
| `cli/main.py` | 抽 `_run_one_turn()` 函数（约 30 行），`run_repl()` 调用它 |
| `tests/cli/conftest.py` | **新增**：`capture_console` fixture |
| `tests/cli/test_dashboard.py` | **新增**：DashboardSection 6 个区块渲染 |
| `tests/cli/test_prompt_area.py` | **新增**：PromptArea + 装饰器链 |
| `tests/cli/test_commands_ui.py` | **新增**：所有 `cmd_*` 斜杠命令输出 |
| `tests/cli/test_lifecycle.py` | **新增**：启动 banner / 调试模式 / 配置错误 / 退出文案 |
| `tests/cli/test_repl_errors.py` | **新增**：`_run_one_turn()` 异常路径（核心） |
| 已有 `test_main.py` | 保留 `_fmt` 测试不动；如需要可补充 markdown/roundtrip |

## 测试场景清单（按文件分组）

### `test_dashboard.py` —— DashboardSection 6 区块

每个区块在 5 种 agent 状态下断言：

- `WelcomeSection`：版本号常驻
- `ModelSection`：provider/model 显示（`openai/gpt-4o`、`anthropic/claude-sonnet-5`）
- `ToolsSection`：
  - `tool_registry=None` → `[dim]无[/dim]`
  - `tool_registry` 空 list → `[dim]无[/dim]`
  - 有 3 个工具，全部 active → 显示全部
  - 有 8 个工具，超过 `max_display=5` → 截断 + `[dim]等 N 个[/dim]`
  - `t.check()` 返回 False → 不显示
- `SkillsSection`：同上结构（含 `skill_registry=None`）
- `ConfigSection`：默认 "默认值" / 传入 `"~/.config/merco/config.json"`
- `SessionSection`：见 cli/main.py 实现（确认渲染函数存在）

### `test_prompt_area.py` —— PromptArea 装饰器链

- 空装饰器 → 输出空
- 单 `ContextBar`（有/无 token 数）
- 多装饰器：注册顺序 = 渲染顺序（验证 use() 行为）
- `agent.token_tracker=None` 等缺失上下文 → 不抛异常
- Panel 包裹验证：`Panel` 包含装饰器组合字符串

### `test_commands_ui.py` —— 斜杠命令输出

每个命令在关键场景下断言：

- `/help` → Panel 含 "帮助"、含命令列表
- `/tools` → 0 工具 / 仅本地 / 仅 MCP / 混合 / 截断
- `/mcp` → 未初始化 / 1 个服务器（🟢）/ 0 个服务器
- `/sessions` → 无历史 / 单条 / 多条 / 当前会话标记
- `/sessions 0` 成功、`/sessions 999` 失败红字、`/sessions abc` 失败
- `/report` → observer=None 灰提示 / observer 有数据 Panel 含 "📊 Session Report"
- `/stats` → 阈值百分比、`is_estimate=True/False` 文案
- `/clear` → `[dim]统计数据已清零[/dim]`
- `/reload` → 成功带 server 数 / 未初始化提示
- `/unknown_command` → `[dim]未知命令: ...[/dim]` + REPL 继续（return True）

### `test_lifecycle.py` —— 生命周期文案

- 启动：`Panel(..., title="🚀 Mercury Code")` 出现
- 调试模式开启：`[yellow]🔍 调试模式已开启[/yellow]`
- 配置缺失：`[yellow]配置未完成，退出[/yellow]`（需要让 `_setup_agent` 走错误路径）
- `init` 子命令：已存在 → `[yellow]配置已存在: ...[/yellow]`；新建成功 → `[green]已创建配置: ...[/green]`
- `setup` 子命令 → 调 `run_setup_wizard()`（至少断言 `merco setup --help` 不挂）
- 退出：`[dim]再见！[/dim]`、`[dim]操作已取消[/dim]`、`[red]错误: ...[/red]`
- `typer --help` 仍可用：`merco run --help` exit 0

### `test_repl_errors.py` —— `agent.run()` 异常路径（核心）

**这是用户最关心的、覆盖薄弱的场景。** `_run_one_turn()` 抽出后覆盖：

| 场景 | 输入 | 期望输出（捕获后断言） |
|---|---|---|
| **正常路径（基线）** | `agent.run()` 返回 `"hi"` | 非 stream：包含 `Panel(Markdown(...))` 含 "hi"；stream：Panel 不打 |
| **非流式 Panel 包裹** | `agent.config.streaming=False`，`run()` 返回含 `**bold**` 的 md | 输出含 "Panel"，含 "bold" 渲染 |
| **流式抑制 Panel** | `agent.config.streaming=True, stream_content=True`，`run()` 返回非空 | 不应再打 Panel；原内容已流式显示 |
| **流式但仍返回** | `agent.config.streaming=True, stream_content=False`，`run()` 返回字符串 | 仍打 Panel（验证 regression） |
| **RuntimeError 友好** | `agent.run()` 抛 `RuntimeError("rate limit")` | 含 `[red]错误: rate limit[/red]`；**不含** `Traceback`；**不含** `File "` |
| **ConnectionError 友好** | `agent.run()` 抛 `ConnectionError("network unreachable")` | 含 `错误`，含 `network unreachable`，不含 traceback |
| **TimeoutError** | `agent.run()` 抛 `asyncio.TimeoutError` | 含 `错误`，Chinese 文案 |
| **CancelledError** | `agent.run()` 抛 `asyncio.CancelledError` | 含 `操作已取消`；**不含** `[red]错误:` |
| **KeyboardInterrupt** | 走到 `except KeyboardInterrupt` | 含 `再见！` |
| **EOFError** | 走到 `except EOFError` | 含 `再见！` |
| **空响应** | `agent.run()` 返回 `""` | Panel 不打，无 crash；REPL 回到读输入 |

每个场景断言三件事：

1. 文案存在（必要）：`assert "错误" in output`
2. traceback 不存在（关键）：`assert "Traceback" not in output`
3. markup 颜色正确（次要）：`assert "[red]" in output` 或 `assert "[dim]" in output`

### `test_main.py` 补充

- `test_main.py` 已有的 `_fmt` 完整保留
- 可选补充：`_fmt` 与实际 Rich 输出再 round-trip 一次（如 `console.print(_fmt(6700))` 后断言 "6.5K" 出现在 buffer）

## 关键设计取舍

| 问题 | 选择 | 理由 |
|---|---|---|
| 断言什么粒度？ | 只断言 Rich markup 标签（`[red]`/`[bold]`） | 颜色码脆，主题换了就坏；markup 文本稳定 |
| 要不要真起 REPL？ | 不要，绕过 typer 直接调内部函数 | CliRunner 跑子命令是已有套路，但注入 fake agent 失败异常几乎做不到；用户最关心的是异常路径 |
| 是否重构 `run_repl()`？ | 最小重构：抽 `_run_one_turn()` | 该函数本身职责清晰（"接收输入+处理异常"），抽出后减小主函数复杂度，不破坏行为 |
| Monkeypatch vs 重构注入？ | monkeypatch 全局 console | 现有代码已经允许 — 单测通过替换全局 console 即可，不需要改业务代码结构 |
| 测 ANSI 颜色码？ | 不测 | 终端主题多变；markup 标签更接近"语义"层面 |
| 测 Panel 边框字符？ | 不测 | 那是 Rich 的责任，测了是在测 Rich |
| 失败时打快照对比？ | 不做 | 第一版只做"包含/不包含"断言；后期可加 golden file 模式，但不要现在引入 |

## 数据流

```
用户输入（fake / 真实）
   │
   ▼
agent.run()  ──── 成功 ──────► Panel(Markdown(response))   [cli/main.py:456]
   │
   └──── 抛异常 ──► 异常分类 ──► 友好渲染 [red]错误: ...[/red]  [cli/main.py:490]
                                              │
                                              ▼
                                      测试断言 (capture buffer)
```

异常路径断言的契约（这是测试钉住的契约，未来谁动了文案测试就会挂）：

| 异常类型 | 必须含 | 必须不含 |
|---|---|---|
| `Exception`（不含下面几类） | `错误: ` + 异常消息 | `Traceback`、`File "`、完整 stacktrace |
| `asyncio.CancelledError` | `操作已取消` | `[red]错误:` |
| `KeyboardInterrupt` / `EOFError` | `再见！` | 任何错误标记 |

## 实现路线

**5 个 PR 串联，单独可合：**

1. **PR1 — 基础设施**：`conftest.py` + `test_dashboard.py`（第 1 层，无外部依赖）
2. **PR2 — 斜杠命令**：`test_commands_ui.py`（用 PR1 fixture）
3. **PR3 — ★ 异常路径**：`cli/main.py` 抽 `_run_one_turn()` + `test_repl_errors.py`（核心）
4. **PR4 — 装饰器与生命周期**：`test_prompt_area.py` + `test_lifecycle.py`
5. **PR5 — 现有测试补强**：`test_main.py` round-trip 测试（可选）

每个 PR 都跑全套件：`uv run pytest tests/cli/ -v`。

## 验收标准

- `uv run pytest tests/cli/ -v` 全绿，新文件无 `skip`/`xfail`
- `test_repl_errors.py` 至少覆盖 11 个异常路径场景
- 任何场景下 `Traceback` 都不会逃逸到 console 输出 —— 这是承诺
- 不依赖截图、不依赖真实 LLM key、不依赖外网

## 风险与缓解

| 风险 | 缓解 |
|---|---|
| `_run_one_turn()` 抽出后行为变了 | PR3 加 PR1+PR2 已有的所有 case 做行为对齐；先 commit 旧测试 + 加新测试，再拆函数 |
| Rich `record=True` 内存泄漏 | 只在 fixture 生命周期内开；测试结束 GC 回收 |
| 临时 console 漏 monkeypatch 某些模块 | fixture 显式 patch `cli.main` 和 `cli.commands`；新模块先 patch 后再加 |
| 颜色 markup 写法变化（如 `[red]错误: {e}[/red]` 改成 `[red]错误：{e}[/red]` 全角冒号） | 这是特性变更；让 PR 失败提醒人去更新文案/测试对 |
| 用户不喜欢"测试当前坏行为" | 设计明确：先钉住现状作为安全网，文案修复单开 PR；对发现的 bad UX 在测试里用 `TODO: user-friendly` 注释说明 |

## 不在范围（YAGNI）

- 不做面板字符宽度对齐断言
- 不做 ANSI 颜色码断言
- 不做面板高度自适应断言
- 不做跨终端（xterm/iterm/wt）兼容断言
- 不做 Rich 主题切换测试
- 不做 web/app.py 的 UI 测试（FastAPI 不在本设计范围）
- 不做 TUI（cli/tui.py 目前是占位）
- 不做 golden file 快照对比（首版只做包含/不包含断言；以后再加）
