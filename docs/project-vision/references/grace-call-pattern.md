# Grace Call 模式（已废弃）

> 参考 Hermes Agent 的 `_budget_grace_call` 机制。实现后验证无效——MiniMax API 不配合。

## Hermes 原始做法

```python
while (api_call_count < max_iterations) or _budget_grace_call:
    response = chat(messages, tools=tools)
    if response.tool_calls:
        execute(tool_calls)
    else:
        return response.content  # 自然收尾
```

## 在 OpenMercury 的验证

2026-05-23 实现后测试：到上限时多给一次正常调用（有工具）→ LLM 继续调工具 → 执行完成后循环退出 → 没收尾文本。

**结论**：Hermes 的模式需要 LLM 在最后自觉给文字回应。MiniMax 不给。

## 教训

- Grace call 依赖 LLM 配合——MiniMax 不配合
- 不要在外面套一层，回来还是得我们自己加 prompt
- 该方案已从代码中完全删除
