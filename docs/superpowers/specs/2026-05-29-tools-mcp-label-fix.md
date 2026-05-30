# /tools Rich markup crash fix

单行。`[mcp:time][/mcp]` 被 Rich 当成未匹配的 closing tag。

通解：动态内容（server name）不放 Rich markup 里，分开打印。

## 改动

`cli/commands.py` L51-52：

```python
# 改前
label = f"[mcp:{toolset[4:]}][/mcp]"

# 改后
label = f"mcp:{toolset[4:]}"  # plain text, no Rich brackets
```
