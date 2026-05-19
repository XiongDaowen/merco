"""任务投递"""

from typing import Callable


class DeliveryManager:
    """任务结果投递管理"""

    def __init__(self):
        self._channels: dict[str, Callable] = {}

    def register_channel(self, name: str, handler: Callable):
        """注册投递渠道（如 telegram, discord, email 等）"""
        self._channels[name] = handler

    async def deliver(self, channel: str, message: str, **kwargs):
        """投递消息到指定渠道"""
        handler = self._channels.get(channel)
        if handler is None:
            return {"error": f"Channel '{channel}' not found"}

        try:
            await handler(message, **kwargs)
            return {"success": True}
        except Exception as e:
            return {"error": str(e)}

    def list_channels(self) -> list[str]:
        """列出可用渠道"""
        return list(self._channels.keys())
