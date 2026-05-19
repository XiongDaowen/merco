"""网关基类"""

from abc import ABC, abstractmethod
from typing import Callable


class BaseGateway(ABC):
    """消息平台网关基类"""

    name: str = ""

    def __init__(self, config: dict):
        self.config = config
        self._message_handler: Callable = None

    def set_handler(self, handler: Callable):
        """设置消息处理器"""
        self._message_handler = handler

    @abstractmethod
    async def start(self):
        """启动网关"""
        pass

    @abstractmethod
    async def stop(self):
        """停止网关"""
        pass

    @abstractmethod
    async def send_message(self, chat_id: str, message: str):
        """发送消息"""
        pass

    async def handle_message(self, chat_id: str, message: str):
        """处理收到的消息"""
        if self._message_handler:
            await self._message_handler(chat_id, message)
