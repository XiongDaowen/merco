"""消息处理与格式化"""

from dataclasses import dataclass, field
from enum import StrEnum


class MessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


@dataclass
class Message:
    """标准消息结构"""

    role: MessageRole
    content: str
    tool_calls: list = field(default_factory=list)
    tool_result: dict | None = None
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """转换为字典格式"""
        result = {"role": self.role.value, "content": self.content}
        if self.tool_calls:
            result["tool_calls"] = self.tool_calls
        if self.tool_result:
            result["tool_result"] = self.tool_result
        return result


class MessageProcessor:
    """消息处理器，负责格式化与转换"""

    @staticmethod
    def format_for_llm(messages: list[Message]) -> list[dict]:
        """格式化为 LLM 可接受的格式"""
        return [msg.to_dict() for msg in messages]

    @staticmethod
    def parse_response(raw: str) -> Message:
        """解析 LLM 响应为 Message 对象"""
        return Message(role=MessageRole.ASSISTANT, content=raw)
