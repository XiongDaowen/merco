"""上下文管理与压缩"""

import re


def estimate_tokens(text: str) -> int:
    """估算 token 数。CJK 约 1.5 token/字，英文约 4 字符/token。"""
    if not text:
        return 0
    cjk = len(re.findall(r'[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff]', text))
    other = len(text) - cjk
    return int(cjk * 1.5 + other / 4)


class ContextManager:
    """管理对话上下文，包括窗口控制与压缩"""

    def __init__(self, max_tokens: int = 128000):
        self.max_tokens = max_tokens
        self.current_tokens = 0
        self.messages = []
        self._overhead_tokens = 0  # system prompt + tool defs 等固定开销
        self.last_actual_tokens = 0  # API 返回的实测 prompt_tokens

    def add(self, message: dict):
        """添加消息到上下文"""
        self.messages.append(message)
        self.current_tokens += self._msg_tokens(message)

    def set_overhead(self, system_prompt: str, tool_count: int):
        """设置固定开销（system prompt + tool definitions）"""
        # system prompt + tool 定义平均 ~200 token/个
        self._overhead_tokens = estimate_tokens(system_prompt) + tool_count * 200

    @property
    def total_tokens(self) -> int:
        """实际发送给 LLM 的 token 估算（消息 + 固定开销）"""
        return self.current_tokens + self._overhead_tokens

    def needs_compression(self) -> bool:
        """判断是否需要压缩"""
        return self.total_tokens > self.max_tokens * 0.8

    def get_window(self, n: int = None) -> list:
        """获取最近 N 条消息"""
        if n is None:
            return self.messages
        return self.messages[-n:]

    @staticmethod
    def _msg_tokens(message: dict) -> int:
        """单条消息 token 估算"""
        content = message.get("content", "")
        if isinstance(content, str):
            return estimate_tokens(content)
        return 0
