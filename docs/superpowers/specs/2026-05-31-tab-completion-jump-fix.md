# Tab 补全跳屏 fix

prompt_toolkit 补全菜单弹出时重绘带动输入框上移。

## 改动

`cli/input_driver.py` PromptSession 参数加 `reserve_space_for_menu=0`，WordCompleter 改为 `sentence=False`。
