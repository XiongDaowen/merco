# 输入层重构 — 设计规格

> prompt_toolkit 替代 readline。粘贴保护 + 自动归档 + 多行输入 + 命令补全。InputDriver 协议为 Phase 4 TUI 预留。

## 动机

当前 `input()` + `readline` 有三问题：
1. 粘贴长文本导致 input 框撕裂 + 自动回车
2. 无多行输入
3. readline 限制了 Phase 4 TUI 演进

## 方案选择

**B + C 组合** — prompt_toolkit + InputDriver 协议。一步到 Phase 4 的输入底座。

## 架构

```
┌────────────────────────────────┐
│  InputDriver（ABC）             │
│  async get_input(prompt) → str │
├────────────────────────────────┤
│  PromptToolkitInput（现在）     │
│  • bracketed paste 保护        │
│  • 长文本自动归档               │
│  • 多行（Alt+Enter）            │
│  • 命令补全（cmd_registry）     │
│  • 历史搜索（Ctrl+R）           │
├────────────────────────────────┤
│  ReadlineInput（fallback）      │
└────────────────────────────────┘
```

## 核心组件

### InputDriver 协议

```python
class InputDriver(ABC):
    @abstractmethod
    async def get_input(self, prompt: str) -> str: ...
```

### PromptToolkitInput

- bracketed paste 检测：prompt_toolkit 原生支持
- 粘贴 ≥ 500 字 → 输入框显示 `[已粘贴 N 字]`，返回原文
- 文件缓存：原文写入 `/tmp/merco_input_{ts}.txt`（给人看，模型拿原文）
- 命令补全：`WordCompleter` 数据源 `cmd_registry.match(text)`
- 多行：`multiline=True`，`Alt+Enter` 换行
- 历史：`FileHistory(~/.merco/input_history)`

### REPL 集成

```python
# 改前
user_input = await asyncio.to_thread(input, prompt)

# 改后
driver = PromptToolkitInput(cmd_registry)
user_input = await driver.get_input(prompt)
```

## 依赖

`pyproject.toml` 加 `prompt-toolkit>=3.0.0`。

## 改动文件

| 文件 | 改动 |
|------|------|
| `cli/input_driver.py` | **新建**：InputDriver + PromptToolkitInput + ReadlineInput |
| `cli/main.py` | 替换 `input()` 调用 |
| `pyproject.toml` | 加 prompt-toolkit 依赖 |

## Phase 4 演进

Textual TUI 实现自己的 `TextualInputDriver`，implements `InputDriver` 协议。`cli/main.py` 一行不改。
