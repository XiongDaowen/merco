# Ctrl+C fix — remove custom binding

自定义 Ctrl+C 绑定和 prompt_toolkit 默认行为冲突，导致重复刷新。

## 改动

1. 删除 `Keys.ControlC` 绑定（自定义的清空+退出逻辑）
2. 删除 `get_input` 里的 `except KeyboardInterrupt`
3. prompt_toolkit 默认 Ctrl+C → 清空输入框（自带行为）
4. OS 信号处理器 → 取消 Agent + 退出计数（不变）

输入框为空时多按几次 Ctrl+C，信号处理器触发退出。
