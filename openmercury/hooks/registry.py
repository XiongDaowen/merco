"""钩子注册与调度"""

from typing import Callable, Awaitable


class HookRegistry:
    """事件钩子注册表"""

    def __init__(self):
        self._hooks: dict[str, list[Callable]] = {}

    def on(self, event: str, handler: Callable):
        """注册钩子处理器"""
        if event not in self._hooks:
            self._hooks[event] = []
        self._hooks[event].append(handler)

    def off(self, event: str, handler: Callable):
        """移除钩子处理器"""
        if event in self._hooks:
            self._hooks[event].remove(handler)

    async def emit(self, event: str, **kwargs):
        """触发事件"""
        handlers = self._hooks.get(event, [])
        for handler in handlers:
            if asyncio.iscoroutinefunction(handler):
                await handler(**kwargs)
            else:
                handler(**kwargs)

    def clear(self, event: str = None):
        """清除钩子"""
        if event:
            self._hooks.pop(event, None)
        else:
            self._hooks.clear()


import asyncio
