"""Telegram 网关"""

from .base import BaseGateway


class TelegramGateway(BaseGateway):
    """Telegram 消息网关"""

    name = "telegram"

    def __init__(self, config: dict):
        super().__init__(config)
        self.bot_token = config.get("bot_token")
        self._bot = None

    async def start(self):
        # TODO: 集成 python-telegram-bot 或 aiogram
        pass

    async def stop(self):
        pass

    async def send_message(self, chat_id: str, message: str):
        # TODO: 实现消息发送
        pass
