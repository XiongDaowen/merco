"""GatewayRegistry - 网关适配器注册表（entries 是活的，需生命周期管理）。"""
from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from merco.gateway.base import GatewayAdapter

logger = logging.getLogger("merco.gateway.registry")


class GatewayRegistry:
    """注册表 + 生命周期管理。

    - ``register`` 重复名 raise（有意 divergence：ModelRegistry 静默覆盖）。
    - ``get`` miss raise KeyError（对齐 ModelRegistry）。
    - entries 是活的：``start_all/stop_all`` 管理 ``adapter.start/stop``。
    - 单个 gateway start/stop 失败隔离（记日志，不影响其他）。
    """

    def __init__(self):
        self._adapters: dict[str, GatewayAdapter] = {}
        self._inbound_handler: Callable[[str, str, str], Awaitable[str]] | None = None

    def register(self, adapter: GatewayAdapter) -> None:
        if not adapter.name:
            raise ValueError("GatewayAdapter must have a non-empty name")
        if adapter.name in self._adapters:
            raise ValueError(f"Gateway already registered: {adapter.name!r}")
        self._adapters[adapter.name] = adapter

    def get(self, name: str) -> GatewayAdapter:
        if name not in self._adapters:
            raise KeyError(f"Unknown gateway: {name!r}")
        return self._adapters[name]

    def list(self) -> list[GatewayAdapter]:
        return list(self._adapters.values())

    def set_inbound_handler(self, handler: Callable[[str, str, str], Awaitable[str]]) -> None:
        """Runtime 在 start_all 前设：每个 adapter 绑定到 runtime.handle_inbound。

        handler 签名 ``(source, chat_id, message) -> reply``（source=adapter.name）。
        """
        self._inbound_handler = handler

    async def start_all(self) -> None:
        """每个 adapter：set_message_handler(bound) -> adapter.start()。单个失败隔离。"""
        if self._inbound_handler is None:
            raise RuntimeError("inbound_handler not set before start_all()")
        for adapter in self._adapters.values():
            name = adapter.name
            # _name=name 默认参在 def 时求值，捕获本轮 adapter 名；
            # 若直接闭包 name 会在循环结束后晚绑定到最后一个 adapter（bug）。
            async def _bound(chat_id: str, message: str, _name=name):
                return await self._inbound_handler(_name, chat_id, message)
            adapter.set_message_handler(_bound)
            try:
                await adapter.start()
            except Exception:
                logger.exception("Gateway %r start failed; isolating", name)

    async def stop_all(self) -> None:
        """停止所有 adapter。start 失败被隔离的 adapter 也会被 stop——因此 adapter 的
        ``stop()`` 必须幂等，且容忍 start() 从未成功的情况（partial-start 清理）。"""
        for adapter in self._adapters.values():
            try:
                await adapter.stop()
            except Exception:
                logger.exception("Gateway %r stop failed; isolating", adapter.name)
