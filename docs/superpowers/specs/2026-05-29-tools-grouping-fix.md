# /tools 统一分组 + 截断后缀 fix

## 问题

1. 内置工具按各自 toolset 分裂成多个 `[内置]` 分组
2. 截断不加 `...`，看起来像被切了

## 改动

`cli/commands.py` cmd_tools handler：

- 分组 key：所有非 MCP toolset → 统一 `"builtin"`
- 截断：`desc[:57] + "..." if len(desc) > 60 else desc`
