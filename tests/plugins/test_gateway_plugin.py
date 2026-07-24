"""GatewayPlugin 测试：激活后注册内置 WebhookGateway。"""

from unittest.mock import MagicMock

from merco.gateway.registry import GatewayRegistry
from merco.gateway.webhook import WebhookGateway
from merco.plugins.base import PluginContext
from merco.plugins.builtin.gateway.plugin import GatewayPlugin


def _make_ctx() -> PluginContext:
    """最小 ctx：gateway_registry 是真 registry，其余 MagicMock。"""
    return PluginContext(
        hooks=MagicMock(),
        tool_registry=MagicMock(),
        prompt_builder=MagicMock(),
        recovery_pipeline=MagicMock(),
        result_pipeline=MagicMock(),
        memory_save_pipeline=MagicMock(),
        recaller=MagicMock(),
        config=MagicMock(),
        gateway_registry=GatewayRegistry(),
    )


async def test_gateway_plugin_registers_webhook():
    ctx = _make_ctx()
    plugin = GatewayPlugin()
    await plugin.activate(ctx)
    gw = ctx.gateway_registry.get("webhook")
    assert isinstance(gw, WebhookGateway)
    assert gw.name == "webhook"


def test_gateway_plugin_metadata():
    p = GatewayPlugin()
    assert p.name == "gateway"
    assert p.priority >= 0
