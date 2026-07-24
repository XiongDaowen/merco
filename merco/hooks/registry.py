"""钩子注册与调度"""

from __future__ import annotations

import inspect
import logging
from dataclasses import dataclass
from typing import Callable

logger = logging.getLogger("merco.hooks.registry")


@dataclass
class HookResult:
    """Hook handler 的结构化返回值。

    data 合并进当前事件 kwargs，后续 handler 会看到更新后的 kwargs。
    stop=True 停止后续 hook handler；业务流程是否短路由调用方决定。
    """

    data: dict | None = None
    stop: bool = False


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

    async def emit(self, event: str, **kwargs) -> HookResult | None:
        """触发事件。

        默认 fire-and-forget：handler 返回 None 时不影响流程。
        handler 可返回 HookResult(data=...) 修改后续 handler 看到的 kwargs。
        handler 可返回 HookResult(stop=True) 停止后续 handler 链。
        """
        handlers = self._hooks.get(event, [])
        current = dict(kwargs)
        changed = False

        for handler in handlers:
            try:
                result = handler(**current)
                if inspect.isawaitable(result):
                    result = await result
            except Exception:
                logger.debug("hook %s handler error", event, exc_info=True)
                continue

            if isinstance(result, HookResult):
                if result.data:
                    current.update(result.data)
                    changed = True
                if result.stop:
                    return HookResult(data=current, stop=True)

        if changed:
            return HookResult(data=current, stop=False)
        return None

    def clear(self, event: str = None):
        """清除钩子"""
        if event:
            self._hooks.pop(event, None)
        else:
            self._hooks.clear()
