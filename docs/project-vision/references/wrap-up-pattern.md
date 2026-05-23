# 收尾模式（当前有效方案）

OpenMercury 的工具预算耗尽收尾机制——历经 15+ 次迭代后的最终简洁方案。

## 核心方法

```python
def _wrap_up_messages(self, messages):
    """追加收尾提示到消息列表末尾"""
    return messages + [{
        "role": "user",
        "content": "已达到最大工具调用次数。请基于已有信息给出最终回复，不要再调用工具。"
    }]

async def _wrap_up_call(self, messages):
    """收尾调用：无工具，清理后返回"""
    resp = await self.llm.chat(messages, tools=[], tool_choice="none")
    content = resp.get("content", "") or "已达到调用上限。"
    self.session.add_message("assistant", content)
    self.context.add({"role": "assistant", "content": content})
    return content
```

## 两处触发点

| 位置 | 条件 | 调用 |
|------|------|------|
| 循环顶部 | `count >= max` | `_wrap_up_call(_wrap_up_messages(messages))` |
| 批量截停 | `count + batch > max` | `_wrap_up_call(_wrap_up_messages(self._build_messages()))` |

## 提示词设计原则（最终版）

```
已达到最大工具调用次数。请基于已有信息给出最终回复，不要再调用工具。
```

1. **放在最后** — 作为 messages 尾部 user 消息，LLM 注意力最高
2. **简短** — 一条信息，不复述、不选项
3. **禁令优先** — "不要再调用工具" 放在指令最后
4. **不解释** — 不说明为什么、不列举选项、不给格式要求

## 幻觉防线（四层独立）

| 层 | 机制 |
|----|------|
| 1 | `tool_choice="none"` — API 层禁止 |
| 2 | `tools=[]` — 无工具可选 |
| 3 | `valid_names=set()` — 始终校验，不依赖 `if tools:` |
| 4 | regex `<\w+:tool_call[^>]*>...</\w+:tool_call>` — 清文本残留 |

## 废弃方案

| 方案 | 问题 |
|------|------|
| Hermes grace call | MiniMax 不配合，LLM 继续调工具 |
| system prompt 注入 | 位置 0 被历史消息淹没 |
| 多段式结构提示 | 越长越容易被复述 |
| `_wrap_up` 精简消息 | 丢失上下文，LLM 不知道在回答什么 |

## 关键教训

- **MiniMax 不遵守 tool_choice** — 这是 provider 硬伤，不是代码能修
- **幻觉校验不留守卫** — `if tools:` 跳过了校验，导致幻觉调用被执行
- **提示词放最后** — LLM 注意力窗口最高的是最新消息，不是 system prompt
- **做新功能先看成熟 Agent** — Hermes/Claude Code/Codex 都用大预算 + 简单收尾
