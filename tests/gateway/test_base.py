"""GatewayAdapter ABC 测试。"""

import pytest

from merco.gateway import GatewayAdapter as ExportedGatewayAdapter  # 验证 __init__ 导出
from merco.gateway.base import GatewayAdapter


def test_gateway_adapter_is_abstract():
    """ABC 不能直接实例化。"""
    with pytest.raises(TypeError):
        GatewayAdapter()


def test_gateway_adapter_exported_from_package():
    """merco.gateway 包导出的 GatewayAdapter 即 base.GatewayAdapter。"""
    assert ExportedGatewayAdapter is GatewayAdapter


def test_subclass_with_abstract_methods_is_concrete():
    """实现全部 abstract 方法后可实例化。"""

    class _Impl(GatewayAdapter):
        name = "impl"

        async def start(self):
            pass

        async def stop(self):
            pass

        async def send_message(self, chat_id, message):
            pass

    adapter = _Impl()
    assert adapter.name == "impl"
    assert adapter.config == {}


def test_set_message_handler_renamed_from_set_handler():
    """set_message_handler 是新方法名；旧 set_handler 不再存在。"""
    assert hasattr(GatewayAdapter, "set_message_handler")
    assert not hasattr(GatewayAdapter, "set_handler"), "旧名 set_handler 应已移除"


def test_handle_message_dropped():
    """concrete handle_message 已删除（inbound 由 adapter 内部直接回调）。"""
    assert not hasattr(GatewayAdapter, "handle_message"), "handle_message 应已删除"


def test_set_message_handler_stores_handler():
    class _Impl(GatewayAdapter):
        name = "impl"

        async def start(self):
            pass

        async def stop(self):
            pass

        async def send_message(self, chat_id, message):
            pass

    adapter = _Impl()

    async def handler(chat_id, message):
        return None

    adapter.set_message_handler(handler)
    assert adapter._message_handler is handler


def test_init_accepts_optional_config():
    class _Impl(GatewayAdapter):
        name = "impl"

        async def start(self):
            pass

        async def stop(self):
            pass

        async def send_message(self, chat_id, message):
            pass

    a1 = _Impl()
    assert a1.config == {}
    a2 = _Impl(config={"port": 9})
    assert a2.config == {"port": 9}
