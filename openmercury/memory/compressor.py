"""上下文压缩器"""


class ContextCompressor:
    """压缩对话历史以节省上下文窗口"""

    def __init__(self, max_tokens: int = 128000):
        self.max_tokens = max_tokens

    async def compress(self, messages: list[dict], strategy: str = "summary") -> list[dict]:
        """压缩消息列表"""
        if strategy == "summary":
            return await self._summarize(messages)
        elif strategy == "truncate":
            return self._truncate(messages)
        else:
            return messages

    async def _summarize(self, messages: list[dict]) -> list[dict]:
        """使用 LLM 摘要压缩"""
        # TODO: 调用 LLM 生成摘要
        if len(messages) <= 2:
            return messages

        # 保留最近的消息，摘要早期消息
        summary = {"role": "system", "content": "[Earlier conversation summarized]"}
        return [summary] + messages[-4:]

    def _truncate(self, messages: list[dict]) -> list[dict]:
        """截断到最近的消息"""
        return messages[-10:]  # 保留最近 10 条
