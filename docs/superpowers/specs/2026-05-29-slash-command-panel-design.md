# `/` 候选命令 — 设计规格

> Tab 补全 + Rich 弹出面板，CommandRegistry 可拓展注册表。Phase 4 换 prompt_toolkit 零重构。

## 动机

当前 CLI 命令是硬编码 `if/elif` 链，`/help` 手动维护。新增命令需改两个地方（handler + help 文本），无 Tab 补全，无法发现命令。

## 架构：三层可替换

```
┌─────────────────────────────────┐
│  UI 层（可替换）                  │
│  Phase 2: readline + Rich Panel  │
│  Phase 4: prompt_toolkit         │
│  数据源: registry.match(text)    │
├─────────────────────────────────┤
│  CommandRegistry（永不变）        │
│  register / match / get_all /    │
│  get_help_text / get             │
├─────────────────────────────────┤
│  命令实现（永不变）               │
│  async def cmd_fork(agent, args) │
└─────────────────────────────────┘
```

## 核心组件

### CommandDef

```python
@dataclass
class CommandDef:
    name: str              # "/fork"
    description: str       # "从当前会话创建分支"
    handler: Callable      # async (agent, args) -> bool
    sub_commands: dict     # {"list": "列出", "<n>": "切换"}
    group: str             # "session" | "info" | "debug"
```

### CommandRegistry

| 方法 | 用途 | 消费者 |
|------|------|--------|
| `register(name, desc, handler, sub, group)` | 注册命令（可做装饰器） | 命令定义 |
| `match(prefix)` → `list[CommandDef]` | 前缀匹配 | Tab 补全 |
| `get_all(group=None)` → `list[CommandDef]` | 全部/按分组 | 弹出面板 |
| `get(name)` → `CommandDef \| None` | 精确查找 | handle_command |
| `get_help_text()` → `str` | 生成帮助文本 | /help 命令 |

三条路径共享同一个数据源——Phase 4 换 UI 层时 registry 不动。

### REPL 集成

- **Tab 补全**：`readline.set_completer()` → `completer(text)` 调 `registry.match(text)`
- **弹出面板**：completer 检测 `text == "/"` → 用 Rich Panel 渲染分组命令（名称 + 简介 + 二级关键词提示）
- **handle_command**：简化为 `registry.get(name).handler(agent, args)`，if/elif 链从 ~180 行缩为 8 行

### 迁移策略

现有 15 个命令从 `cli/main.py` 的 `if/elif` 链迁移到 `cli/commands.py`（装饰器定义 + async handler）。新增命令只需一行装饰器。

## 改动文件

| 文件 | 改动 |
|------|------|
| `cli/registry.py` | **新建**：CommandDef + CommandRegistry |
| `cli/commands.py` | **新建**：全部命令定义 |
| `cli/main.py` | 简化 handle_command，加 readline completer |

## 边界情况

| 场景 | 行为 |
|------|------|
| 输入 `/` + Tab | 弹出面板 + 开始补全 |
| 输入 `/ses` + Tab | 补全为 `/sessions` |
| 输入 `/sessions ` + Tab | 展示子命令：list / <n> / delete |
| 空输入 + Tab | 不触发（命令前缀不匹配） |
| 未知命令 | 原有 fallback 提示不变 |
| Phase 4 迁移 | registry 零改动，只换 UI 层的 50 行 |
