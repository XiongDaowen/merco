"""聊天钩子"""

from .registry import HookRegistry


def register_chat_hooks(registry: HookRegistry):
    """注册聊天相关钩子"""

    @registry.on("message.receive")
    async def on_message_receive(message: str, **kwargs):
        """收到用户消息"""
        pass

    @registry.on("message.send")
    async def on_message_send(response: str, **kwargs):
        """发送助手回复"""
        pass

    @registry.on("context.compact")
    async def on_context_compact(strategy: str, **kwargs):
        """上下文压缩触发"""
        pass
