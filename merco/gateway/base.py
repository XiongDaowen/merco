"""网关适配器基类"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable


class GatewayAdapter(ABC):
    """消息平台网关适配器基类。

    inbound: adapter 收到消息后回调 ``message_handler(chat_id, message) -> reply``（async）。
    outbound: ``send_message(chat_id, message)`` 发出站消息。
    ``set_message_handler`` 由 ``GatewayRegistry.start_all()`` 绑定到
    ``runtime.handle_inbound(adapter.name, chat_id, message)``。
    """

    name: str = ""

    def __init__(self, config: dict | None = None):
        self.config = config or {}
        self._message_handler: Callable[[str, str], Awaitable[str]] | None = None

    def set_message_handler(self, handler: Callable[[str, str], Awaitable[str]]) -> None:
        """设置 inbound 消息处理器（由 GatewayRegistry.start_all 绑定）。"""
        self._message_handler = handler

    @abstractmethod
    async def start(self) -> None:
        """启动网关（如起 HTTP 服务监听）。"""

    @abstractmethod
    async def stop(self) -> None:
        """停止网关。"""

    @abstractmethod
    async def send_message(self, chat_id: str, message: str) -> None:
        """出站：发送消息到 chat_id。"""
