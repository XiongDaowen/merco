"""上下文管理与压缩"""


class ContextManager:
    """管理对话上下文，包括窗口控制与压缩"""

    def __init__(self, max_tokens: int = 128000):
        self.max_tokens = max_tokens
        self.current_tokens = 0
        self.messages = []

    def add(self, message: dict):
        """添加消息到上下文"""
        self.messages.append(message)
        self.current_tokens += self._estimate_tokens(message)

    def needs_compression(self) -> bool:
        """判断是否需要压缩"""
        return self.current_tokens > self.max_tokens * 0.8

    def compress(self, strategy: str = "summary") -> list:
        """压缩上下文"""
        raise NotImplementedError

    def get_window(self, n: int = None) -> list:
        """获取最近 N 条消息"""
        if n is None:
            return self.messages
        return self.messages[-n:]

    @staticmethod
    def _estimate_tokens(message: dict) -> int:
        """粗略估算 token 数量"""
        content = message.get("content", "")
        return len(content) // 4  # 粗略估算：4 字符 ≈ 1 token


class ContextCompressor:
    """上下文压缩器"""

    async def summarize(self, messages: list) -> str:
        """将消息列表压缩为摘要"""
        raise NotImplementedError

    async def extract_key_points(self, messages: list) -> list:
        """提取关键信息点"""
        raise NotImplementedError
