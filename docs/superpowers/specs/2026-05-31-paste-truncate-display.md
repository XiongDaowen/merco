# 粘贴显示截断 fix — spec

粘贴长文本时，输入框只显示 `[已粘贴 N 字]` 标记，原文透传给 LLM。

## 改动

`cli/input_driver.py` PromptToolkitInput：paste 检测 + buffer 替换 + 原文返回。

- `_paste_stash`：存原文
- buffer `on_text_changed` 钩子：超过阈值 → 存原文到 stash → buffer 换标记
- `get_input`：如有 stash → 返回原文而非标记 → 清 stash
