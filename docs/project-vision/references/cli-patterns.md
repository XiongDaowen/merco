# CLI 交互模式踩坑集

> 2026-05-22，大量 CLI 交互问题集中修复。记录关键模式和坑，避免重复踩。

## 信号处理：Ctrl+C 退出

**目标**：两段式退出 — 第一次 Ctrl+C 取消任务，第二次退出；空闲时第一次提醒，第二次退出。

**核心难题**：`input()` 是 C 阻塞调用。信号处理器能设 flag，但 `input()` 不返回就永远不会读到 flag。"按任意键取消" 在 `input()` 架构下是伪需求——字符在 C buffer 里，Python 代码跑不到。

**最终方案：`_readline()` 替代 `input()`**

```python
def _readline(exit_flag_ref: list):
    """逐字符读取，50ms 轮询 exit_flag。在线程中运行。"""
    import select
    line_chars = []
    while True:
        if exit_flag_ref[0]:
            # 清空 stdin 残余 → 返回 cancelled
            _drain_stdin()
            return ("", True)
        ready, _, _ = select.select([sys.stdin], [], [], 0.05)
        if not ready:
            continue
        ch = sys.stdin.read(1)
        if ch in ("\n", "\r"): return ("".join(line_chars), False)
        if ch == "\x7f" and line_chars: line_chars.pop(); sys.stdout.write("\b \b")
        if ord(ch) >= 32: line_chars.append(ch); sys.stdout.write(ch)
```

关键设计点：
1. **`select` 50ms 超时** — 不阻塞，轮询间隔内 exit_flag 变化立即感知
2. **`exit_flag_ref` 是单元素列表** — 信号处理器和读线程共享可变引用，绕过 nonlocal 跨线程限制
3. **stdin 清空** — 返回 cancelled 前 `tty.setraw(0)` → `read(1024)` → 恢复，避免残余字符污染下一行
4. **Backspace 支持** — `\x7f` → `\b \b` 原样回显删除
5. **通过 `asyncio.to_thread(_readline, exit_flag)` 调用** — 不阻塞 event loop

**取消退出流程**：
```
1. Ctrl+C → exit_flag[0]=True → _readline 50ms 内返回 ("", True)
2. repl 看到 cancelled → exit_flag[0]=False → continue → 新 prompt
3. 用户输入的内容被 stdin drain 清掉，不进入下一轮
```

**错误路径归档**：
- `loop.call_soon(loop.stop)` — asyncio.run() 清理时 loop 已死 → RuntimeError
- `signal.SIG_DFL` + `raise_signal` — 直接杀进程，Python 异常处理不跑
- `input()` + exit_flag 布尔值 — input() 阻塞，flag 改了但读不到
- `write_file` 覆盖整个文件 — 300 行变 100 行碎片。局部改动用 `patch` 工具。

## 终端设置：控制字符回显

**问题**：Ctrl+C 会在终端显示 `^C`
**方案**：`termios.ECHOCTL` 关闭控制字符回显
```python
old = termios.tcgetattr(0)
new = termios.tcgetattr(0)
new[3] = new[3] & ~termios.ECHOCTL
termios.tcsetattr(0, termios.TCSADRAIN, new)
```

**恢复是必须的**：退出时 `os._exit(0)` 跳过 finally → 必须在 `_exit` 前手动恢复终端。忘记恢复会留一个看不见打字的终端（`stty echo` 可救）。

## Rich 输出：spinner 与工具日志冲突

**问题**：`console.status("思考中")` 的 spinner 会在每个 `console.print()` 行前重复出现
**根因**：Rich 的 status 用 ANSI 逃逸码管理光标，同一 stdout 上的 `console.print` 会打乱渲染

**解法**：工具调用日志走 stderr
```python
print(f"  ⚙ {tool_name} ...", file=sys.stderr, flush=True)
```
- stderr 和 stdout 是独立流，不互相干扰
- 用 `print()` 而不是 Rich 的 `console.print()`，避免 ANSI 码问题

## 工具调用显示优化

**最终方案：key=value + 终端宽度动态截断 + dim ANSI + stderr**

```python
progress = f"{self._tool_calls_count + 1}/{self._max_tool_calls}"
arg_parts = [f"{k}={v}" for k, v in arguments.items()]
arg_str = ", ".join(arg_parts)
# 终端宽度动态截断
prefix = f"  ⚙ {tool_name} ({progress}) "
term_w = shutil.get_terminal_size().columns or 80
max_width = term_w - len(prefix) - 1
if len(arg_str) > max_width:
    arg_str = arg_str[:max_width - 3] + "..."
print(f"\x1b[2m{prefix}{arg_str}\x1b[0m", file=sys.stderr, flush=True)
```

设计要点：
1. **key=value 不用 json.dumps** — JSON 转义是序列化需求，显示是另一个需求。`json.dumps()` 会转义 `"` → `\"`、中文 → `\uXXXX`，事后 replace 永远修不完
2. **`\x1b[2m` dim** — 工具日志低调灰色，不抢眼
3. **stderr** — 与 Rich 的 stdout 输出隔离，不干扰 rule/Markdown 渲染
4. **`shutil.get_terminal_size`** — 窄终端 80 列紧凑，宽终端 200+ 列显示更多参数
5. **完整参数** — 进 `logger.debug`，`--debug` 可见

## readline：一行解决光标/历史

`import readline` 即可启用 `input()` 的：
- 上下箭头翻历史
- 左右箭头移动光标
- Home/End 行首行尾
- Backspace/Delete 正常删除，不越界

Linux 自带，无需额外安装。

## Markdown 渲染

```python
from rich.markdown import Markdown
console.print(Markdown(response))
```
Rich 自动着色代码块、标题、列表、粗体斜体。

## 子命令 vs 无参启动

Typer 用 `@app.callback(invoke_without_command=True)` 让直接敲 `openmercury` 进入交互模式：
```python
@app.callback(invoke_without_command=True)
def main_callback(ctx: typer.Context, ...):
    if ctx.invoked_subcommand is not None:
        return
    # 无子命令 = 交互模式
```
`run` 保持为显式子命令，与 callback 共享 `_setup_agent()` 工厂函数。

## 配置化优于硬编码


## 视觉分界：rule 分隔 + 无 spinner + key=value 参数

**最终视觉架构**（多轮迭代后稳定）：
```
──── Agent ────                              ← 第一条输出自动开始（不显示此标签）
(LLM 中间文字，Markdown 渲染)                 ← 仅模型自己决定何时说
  ⚙ bash (3/15) command=curl wttr.in         ← stderr，dim，key=value 无转义
  ⚙ read_file (4/15) path=result.json        ← 终端宽度动态截断
                                              ← 空行呼吸
────────────────────────────────────────────  ← dim rule
(最终回复 Markdown 渲染)                       ← Rich Markdown
────────────────────────────────────────────  ← dim rule

> 用户输入                                   ← bold cyan ANSI + \x01/\x02 readline 标记
```

设计决策：
- **不用 spinner** — 第一条输出（中间文字或工具调用）自证"在干活"，`思考中` 冗余
- **不用 "Agent" 标签 rule** — 第一条工具调用已标记输出区开始
- **工具参数 key=value** — 不用 `json.dumps()` 做显示（JSON 转义是序列化需求，显示是另一个需求）
- **rule 分隔** — `console.rule(style="dim")` 框出最终回复区，上下各一道
- **ANSI prompt** — `input("\n\x01\x1b[1;36m\x02> \x01\x1b[0m\x02")`，bold cyan，readline 正确计宽

## Rich 输出：spinner 已移除

当前方案：不用 spinner。工具日志走 stderr（dim ANSI `\x1b[2m`），响应走 Rich Markdown + rule。第一条输出自然替代"思考中"。

历史记录（spinner 方案，已废弃）：工具调用日志走 stderr，spinner 跑在 `console.status()` 的 stdout context 中。废弃原因：spinner 在纯工具调用场景是噪音。
- 文字即时渲染给用户看
- 完整内容也放入消息上下文（API 需要）


## 配置化优于硬编码

`max_tool_calls`、`retry_delays`、`cooldown` 等运行时参数不应硬编码在代码中。通过 `OpenMercuryConfig` 暴露为 `openmercury.json` 的可配置项，便于不同 provider/场景调优。
```python
# ✅ 从配置读取
self._max_tool_calls = config.max_tool_calls
# ❌ 硬编码
self._max_tool_calls = 20
```
