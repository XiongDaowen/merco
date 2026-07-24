"""MiniMax built-in plugin.

注入 MiniMaxProvider：包装 OpenAICompatibleProvider，在 MiniMax 协议异常
（模型在 <think> 内就开始给用户回复）时把 thinking 提取后的 content 补回去。
"""

from .plugin import MiniMaxPlugin

__all__ = ["MiniMaxPlugin"]
