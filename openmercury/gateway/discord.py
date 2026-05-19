"""Discord 网关"""

from .base import BaseGateway


class DiscordGateway(BaseGateway):
    """Discord 消息网关"""

    name = "discord"

    def __init__(self, config: dict):
        super().__init__(config)
        self.bot_token = config.get("bot_token")

    async def start(self):
        # TODO: 集成 discord.py
        pass

    async def stop(self):
        pass

    async def send_message(self, chat_id: str, message: str):
        # TODO: 实现消息发送
        pass
