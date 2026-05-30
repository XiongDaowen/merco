# /tools 换行符过滤

单行。tool description 中的 `\n` 替换为空格。

## 改动

`cli/commands.py` L61: `raw = t.description or ""` 改为 `raw = (t.description or "").replace("\n", " ")`
