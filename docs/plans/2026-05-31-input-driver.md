# 输入层重构 — 实现计划

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** prompt_toolkit 替代 readline：粘贴保护 + 多行 + 命令补全 + InputDriver 协议。

**Architecture:** InputDriver ABC → PromptToolkitInput → 替换 cli/main.py 的 `input()`。

**Tech Stack:** prompt_toolkit>=3.0.0, Python 3.12+

---

### Task 1: 加依赖 + InputDriver 协议

**Objective:** pyproject.toml 加 prompt-toolkit。新建 `cli/input_driver.py`。

**Files:**
- Modify: `pyproject.toml`
- Create: `cli/input_driver.py`

**Step 1: pyproject.toml**

在 dependencies 列表加 `"prompt-toolkit>=3.0.0",`

**Step 2: cli/input_driver.py**

```python
"""终端输入抽象。Phase 2: PromptToolkitInput。Phase 4: Textual 直接复用。"""

from abc import ABC, abstractmethod


class InputDriver(ABC):
    """终端输入抽象。"""

    @abstractmethod
    async def get_input(self, prompt: str) -> str:
        """获取一行用户输入，可含多行。"""
        ...
```

**Step 3: 安装依赖 + 验证**

```bash
uv pip install prompt-toolkit
uv run python -c "import prompt_toolkit; from cli.input_driver import InputDriver; print('OK')"
```

**Step 4: Commit**

```bash
git commit -m "feat(input): add prompt_toolkit dependency + InputDriver protocol"
```

---

### Task 2: PromptToolkitInput 实现

**Objective:** 实现 PromptToolkitInput：粘贴保护 + 多行 + 命令补全 + 历史。

**Files:**
- Modify: `cli/input_driver.py`

**Step 1: 实现**

```python
import os
import time
from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.keys import Keys
from prompt_toolkit.styles import Style
from pathlib import Path


_PASTE_THRESHOLD = 500  # 超过此字符数触发粘贴归档


class PromptToolkitInput(InputDriver):
    """prompt_toolkit 实现：粘贴保护 + 多行 + 命令补全 + 历史搜索"""

    def __init__(self, commands: list[str] | None = None):
        hist_path = os.path.expanduser("~/.merco/input_history")
        os.makedirs(os.path.dirname(hist_path), exist_ok=True)

        completer = WordCompleter(commands or [], sentence=True)

        bindings = KeyBindings()

        @bindings.add(Keys.Escape, Keys.Enter)
        def _(event):
            """Alt+Enter: insert newline for multiline input"""
            event.current_buffer.insert_text("\n")

        self._session = PromptSession(
            history=FileHistory(hist_path),
            completer=completer,
            key_bindings=bindings,
            style=Style.from_dict({
                "prompt": "bold",
                "completion-menu.completion": "bg:#444 #fff",
            }),
        )

    async def get_input(self, prompt: str) -> str:
        # prompt_toolkit 的 PromptSession.prompt_async 已经是 async，直接 await
        from prompt_toolkit.shortcuts import prompt as pt_prompt

        text = await self._session.prompt_async(
            prompt,
            # bracketed paste 原生支持——prompt_toolkit 自动检测粘贴
            # 长文本在输入缓冲里正常处理，不撕裂
        )

        # 粘贴归档：如果用户输入超过阈值，存一份到文件（给人看）
        if len(text) >= _PASTE_THRESHOLD:
            self._save_paste(text)

        return text

    def _save_paste(self, text: str) -> None:
        tmpdir = os.path.expanduser("~/.merco/pastes")
        os.makedirs(tmpdir, exist_ok=True)
        ts = int(time.time() * 1000)
        path = os.path.join(tmpdir, f"{ts}.txt")
        Path(path).write_text(text, encoding="utf-8")

    def update_commands(self, commands: list[str]) -> None:
        """动态更新命令补全词表"""
        self._session.completer = WordCompleter(commands, sentence=True)
```

**Step 2: 验证**

```bash
uv run python -c "from cli.input_driver import PromptToolkitInput; print('OK')"
```

**Step 3: Commit**

```bash
git commit -m "feat(input): PromptToolkitInput with paste protection + multiline + completion"
```

---

### Task 3: REPL 集成 — 替换 input()

**Objective:** cli/main.py 用 PromptToolkitInput 替代 `asyncio.to_thread(input, ...)`。

**Files:**
- Modify: `cli/main.py`

**Step 1: 改动 run_repl()**

删除 readline completer（`_setup_readline_completer`），改用 driver：

```python
# 在 run_repl() 开头，import cli.commands 之后：
from cli.input_driver import PromptToolkitInput

def run_repl(agent, dashboard=None, config_source=""):
    ...
    import cli.commands
    driver = PromptToolkitInput([c.name for c in cmd_registry.get_all()])
    # 删除 _setup_readline_completer() 调用

    async def repl():
        ...
        # 替换：
        # user_input = await asyncio.to_thread(input, prompt)
        # 改为：
        user_input = await driver.get_input(prompt)
```

同时更新 `/reload-mcp` 命令——MCP 重载后新工具也加入补全。

**Step 2: 删除不再需要的 readline import + setup 函数**

删除 `import readline`，删除 `_setup_readline_completer()` 函数体。

**Step 3: 手动验证**

```bash
merco
# 测试:
# - 粘贴长文本（≥500 字）
# - Alt+Enter 多行
# - / + Tab 补全
# - Ctrl+R 历史搜索
```

**Step 4: Commit**

```bash
git commit -m "feat(input): replace readline with PromptToolkitInput in REPL"
```

---

## Task Order

```
Task 1: 依赖 + 协议     ← 无依赖
Task 2: PromptToolkitInput ← 依赖 Task 1
Task 3: REPL 集成         ← 依赖 Task 1+2
```
