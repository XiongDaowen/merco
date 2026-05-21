# CLI Display Patterns

Established conventions for OpenMercury's CLI output. Change these here, not ad-hoc in code.

## Output Structure

```
> 用户输入

─── Agent ──────────────  ← console.rule("[bold]Agent[/bold]", style="dim")
  ⠋ bash (1/15) command=find /...  ← Live, spinner动画, bright_black
  ✓ bash (1/15) command=find /...  2.3s  ← 同行更新，定时
╭────────────────────────╮
│ 中间文字（LLM tool 附带） │  ← Panel(Markdown(...), border_style="dim")
╰────────────────────────╯
  ✓ read_file (2/15) path=...  0.1s
╭────────────────────────╮
│ 最终回复                │  ← Panel(Markdown(response), border_style="dim")
╰────────────────────────╯
──────────────────────────  ← console.rule(style="dim")
```

## Tool Call Display

- Format: `✓ tool_name (N/M) key1=val1, key2=val2` (bright_black)
- Use `key=value` pairs, NOT `json.dumps()` — avoids `\"` and `\n` escapes
- Dynamic truncation: calculates full line (incl. `✓ ... 99.9s`) then truncates to fit terminal
- In-place update via `Live`:
  - Running: `⠋ tool_name (N/M) args...` → spinner cycles `⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏`
  - Done: `✓ tool_name (N/M) args...  2.3s` → same line, timing appended
- No folding — every call shown individually
- Colors via `Text.from_markup(f"[bright_black]...[/bright_black]")`

## Exit / Ctrl+C

- Two-stage: first Ctrl+C during idle → warning, second → exit
- Use `exit_count` int counter in signal handler (0 → 1 → 2 = exit)
- Exit hooks pattern: `_on_exit(fn)` / `_run_exit_hooks()` → runs regardless of exit path
- `os._exit(0)` after `_run_exit_hooks()` for forced exit
- `termios.ECHOCTL` bit cleared to suppress `^C` terminal echo
- Restore terminal via exit hook: `_on_exit(lambda: termios.tcsetattr(...))`

## Input

- `import readline` — gives history, cursor movement, boundary protection
- `asyncio.to_thread(input, "\n> ")` — prompt via ANSI, \x01/\x02 markers for readline
- prompt: `"\n\x01\x1b[1;36m\x02> \x01\x1b[0m\x02"` — bold cyan `>`
- Do NOT character-by-character read (tried `select`/`_readline`, over-engineered, WSL issues)

## Response Rendering

- Use `console.print(Panel(Markdown(response), border_style="dim"))` — boxed with ┌┐└┘
- Intermediate text from LLM (content alongside tool_calls): same Panel wrapping
- No "思考中" spinner — first output (tool call or text) signals activity

## Pitfalls

- `write_file` overwrites ENTIRE file; use `patch` for targeted edits
- `console.print` with Rich markup doesn't work as `input()` prompt; use raw ANSI
- `os._exit(0)` skips `finally` blocks; call `_run_exit_hooks()` before it
- `loop.add_signal_handler` suppresses default KeyboardInterrupt; handle explicitly
- stderr/stdout interleaving breaks Rich's cursor management; keep everything on stdout
- Don't put debug logs ("上次 10 不够") as code comments; document in skill references instead
