"""GatewayRegistry 测试：register/get/list + 生命周期 + handler 绑定 + 失败隔离。"""

import logging

import pytest

from merco.gateway.base import GatewayAdapter
from merco.gateway.registry import GatewayRegistry


class _FakeGateway(GatewayAdapter):
    """记录 start/stop 调用的假网关。"""

    def __init__(self, name="fake"):
        super().__init__()
        self.name = name
        self.started = False
        self.stopped = False
        self.handler_bound = None

    async def start(self):
        self.started = True

    async def stop(self):
        self.stopped = True

    async def send_message(self, chat_id, message):
        pass

    def set_message_handler(self, handler):
        self.handler_bound = handler
        super().set_message_handler(handler)


def test_register_and_get():
    reg = GatewayRegistry()
    gw = _FakeGateway("w")
    reg.register(gw)
    assert reg.get("w") is gw


def test_register_duplicate_raises():
    reg = GatewayRegistry()
    reg.register(_FakeGateway("w"))
    with pytest.raises(ValueError):
        reg.register(_FakeGateway("w"))


def test_register_empty_name_raises():
    reg = GatewayRegistry()
    with pytest.raises(ValueError):
        reg.register(_FakeGateway(""))


def test_get_missing_raises_keyerror():
    reg = GatewayRegistry()
    with pytest.raises(KeyError):
        reg.get("nope")


def test_list_returns_all():
    reg = GatewayRegistry()
    reg.register(_FakeGateway("a"))
    reg.register(_FakeGateway("b"))
    names = {g.name for g in reg.list()}
    assert names == {"a", "b"}


async def test_start_all_binds_handler_and_starts_each():
    """start_all 给每个 adapter 绑 inbound handler（含 adapter.name）并 start。"""
    reg = GatewayRegistry()
    gw = _FakeGateway("w")
    reg.register(gw)

    received = []

    async def inbound(source, chat_id, message):
        received.append((source, chat_id, message))
        return "ok"

    reg.set_inbound_handler(inbound)
    await reg.start_all()

    assert gw.started is True
    # 绑定的 handler 调用时应转发到 inbound(source=gw.name, ...)
    assert gw.handler_bound is not None
    reply = await gw.handler_bound("c1", "hi")
    assert reply == "ok"
    assert received == [("w", "c1", "hi")]
    await reg.stop_all()
    assert gw.stopped is True


async def test_start_all_binds_per_adapter_name_no_late_binding():
    """多个 adapter 时，每个绑定的 handler 转发各自 name（不晚绑到最后一个）。

    这是 _bound 闭包 _name=name 默认参的关键正确性属性：若直接闭包 name，
    所有 adapter 都会转发循环结束后的最后一个 name。
    """
    reg = GatewayRegistry()
    gw_a = _FakeGateway("a")
    gw_b = _FakeGateway("b")
    gw_c = _FakeGateway("c")
    for gw in (gw_a, gw_b, gw_c):
        reg.register(gw)

    received = []

    async def inbound(source, chat_id, message):
        received.append(source)
        return "ok"

    reg.set_inbound_handler(inbound)
    await reg.start_all()

    # 每个 adapter 的 handler 转发各自的 name，而非全部晚绑到 "c"
    await gw_a.handler_bound("c1", "m")
    await gw_b.handler_bound("c1", "m")
    await gw_c.handler_bound("c1", "m")
    assert received == ["a", "b", "c"], "各 adapter 应转发各自 name，非晚绑到最后"
    await reg.stop_all()


async def test_start_all_without_handler_raises():
    reg = GatewayRegistry()
    reg.register(_FakeGateway("w"))
    with pytest.raises(RuntimeError):
        await reg.start_all()


async def test_start_all_isolates_single_failure(caplog):
    """一个 gateway start 失败不影响其他，且失败被记 ERROR 日志。"""

    class _BoomGateway(_FakeGateway):
        async def start(self):
            raise RuntimeError("boom")

    reg = GatewayRegistry()
    boom = _BoomGateway("boom")
    good = _FakeGateway("good")
    reg.register(boom)
    reg.register(good)

    async def inbound(source, chat_id, message):
        return "ok"

    reg.set_inbound_handler(inbound)

    with caplog.at_level(logging.ERROR, logger="merco.gateway.registry"):
        await reg.start_all()  # 不抛
    assert good.started is True  # good 仍启动
    # boom 的失败被记日志（隔离可观测）
    assert any("boom" in r.message for r in caplog.records), "boom start 失败应记 ERROR 日志"
    await reg.stop_all()
