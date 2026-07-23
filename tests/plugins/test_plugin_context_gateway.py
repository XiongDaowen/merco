"""PluginContext.register_gateway 测试。"""
from unittest.mock import MagicMock

import pytest

from merco.gateway.base import GatewayAdapter
from merco.gateway.registry import GatewayRegistry
from merco.plugins.base import PluginContext


class _Gw(GatewayAdapter):
    name = "gw"
    async def start(self): pass
    async def stop(self): pass
    async def send_message(self, chat_id, message): pass


def _make_ctx(gateway_registry=None) -> PluginContext:
    """最小 PluginContext（其余依赖传 MagicMock）。"""
    return PluginContext(
        hooks=MagicMock(), tool_registry=MagicMock(), prompt_builder=MagicMock(),
        recovery_pipeline=MagicMock(), result_pipeline=MagicMock(),
        memory_save_pipeline=MagicMock(), recaller=MagicMock(), config=MagicMock(),
        gateway_registry=gateway_registry,
    )


def test_register_gateway_delegates_to_registry():
    reg = GatewayRegistry()
    ctx = _make_ctx(gateway_registry=reg)
    gw = _Gw()
    ctx.register_gateway(gw)
    assert reg.get("gw") is gw


def test_register_gateway_raises_when_no_registry():
    ctx = _make_ctx(gateway_registry=None)
    with pytest.raises(RuntimeError):
        ctx.register_gateway(_Gw())


def test_context_holds_gateway_registry():
    reg = GatewayRegistry()
    ctx = _make_ctx(gateway_registry=reg)
    assert ctx.gateway_registry is reg
