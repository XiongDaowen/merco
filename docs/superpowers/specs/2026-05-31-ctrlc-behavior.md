# Ctrl+C 三态行为 spec

## 行为

| 状态 | Ctrl+C |
|------|--------|
| Agent 运行中 | 取消当前任务（现有行为不变） |
| 输入框有内容 | 清空输入框 |
| 输入框为空 | 退出（第一次提示，第二次退出） |

## 改动

`cli/input_driver.py` PromptToolkitInput：
- 加 `Keys.ControlC` 绑定：有内容 → 清空，无内容 → 抛 `KeyboardInterrupt`
- `get_input` 捕获 `KeyboardInterrupt` → 返回 `""`

`cli/main.py` REPL：
- 空输入 `continue`（原有逻辑）已支持 exit_count
- 信号处理器保留（Agent 运行时取消任务）
