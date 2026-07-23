"""AgentRuntime 测试：start/stop 幂等 + handle_inbound/submit 路由 + scheduler task + 失败隔离。"""
import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from merco.core.runtime import AgentRuntime
from merco.gateway.base import GatewayAdapter
from merco.gateway.registry import GatewayRegistry


class _FakeGateway(GatewayAdapter):
    def __init__(self, name="fake", boom=False):
        super().__init__()
        self.name = name
        self.boom = boom
        self.started = False
        self.stopped = False

    async def start(self):
        if self.boom:
            raise RuntimeError("boom")
        self.started = True

    async def stop(self):
        self.stopped = True

    async def send_message(self, chat_id, message):
        pass


class _FakeScheduler:
    def __init__(self):
        self.started = False
        self.stopped = False

    async def start(self):
        self.started = True

    async def stop(self):
        self.stopped = True


async def _wait_for(predicate, *, tries=50, delay=0.01):
    for _ in range(tries):
        if predicate():
            return True
        await asyncio.sleep(delay)
    return predicate()


def _make_runtime(*, gateway=None, scheduler=None, agent_run_return="reply"):
    """构造 Runtime + 假 agent（plugin_ctx 暴露 gateway_registry + scheduler）。"""
    reg = GatewayRegistry()
    if gateway is not None:
        reg.register(gateway)
    sched = scheduler or _FakeScheduler()

    agent = MagicMock()
    agent.run = AsyncMock(return_value=agent_run_return)
    agent.hooks = MagicMock()
    agent.hooks.emit = AsyncMock()

    class _Ctx:
        pass

    ctx = _Ctx()
    ctx.scheduler = sched
    ctx.gateway_registry = reg
    agent.plugin_ctx = ctx

    runtime = AgentRuntime(config=MagicMock(), agent=agent)
    return runtime, agent, reg, sched


async def test_start_starts_gateway_and_scheduler():
    runtime, agent, reg, sched = _make_runtime(gateway=_FakeGateway("w"))
    await runtime.start()
    # scheduler 在后台 task 里 start()；轮询等它跑一轮
    await _wait_for(lambda: sched.started)
    assert reg.get("w").started is True
    assert sched.started is True
    await runtime.stop()


async def test_start_is_idempotent():
    runtime, *_ = _make_runtime(gateway=_FakeGateway("w"))
    await runtime.start()
    await runtime.start()  # 第二次 no-op
    await runtime.stop()


async def test_stop_is_idempotent():
    runtime, *_ = _make_runtime(gateway=_FakeGateway("w"))
    await runtime.start()
    await runtime.stop()
    await runtime.stop()  # 不抛


async def test_handle_inbound_routes_to_agent_run():
    runtime, agent, *_ = _make_runtime(gateway=_FakeGateway("w"))
    await runtime.start()
    reply = await runtime.handle_inbound("webhook", "c1", "hi")
    assert reply == "reply"
    agent.run.assert_awaited_once_with("hi")  # 单 session：message 直传
    await runtime.stop()


async def test_submit_routes_to_agent_run():
    runtime, agent, *_ = _make_runtime(gateway=_FakeGateway("w"))
    await runtime.start()
    reply = await runtime.submit("do something")
    assert reply == "reply"
    agent.run.assert_awaited_with("do something")
    await runtime.stop()


async def test_start_all_binds_handle_inbound_as_gateway_handler():
    """gateway 收到 (chat_id, msg) -> runtime.handle_inbound(gw.name, chat_id, msg)。"""
    runtime, agent, reg, *_ = _make_runtime(gateway=_FakeGateway("w"))
    await runtime.start()
    gw = reg.get("w")
    # 模拟 gateway inbound：调绑定的 handler
    assert gw._message_handler is not None
    reply = await gw._message_handler("c1", "hi")
    assert reply == "reply"
    agent.run.assert_awaited_once_with("hi")
    await runtime.stop()


async def test_single_gateway_failure_isolated():
    """一个 gateway start 失败，另一个仍启动，runtime.start 不抛。"""
    runtime, agent, reg, *_ = _make_runtime(gateway=None)
    reg.register(_FakeGateway("boom", boom=True))
    reg.register(_FakeGateway("good"))
    await runtime.start()  # 不抛
    assert reg.get("good").started is True
    await runtime.stop()


async def test_stop_stops_gateway_and_scheduler():
    runtime, agent, reg, sched = _make_runtime(gateway=_FakeGateway("w"))
    await runtime.start()
    await runtime.stop()
    assert reg.get("w").stopped is True
    assert sched.stopped is True
    # 宿主 teardown 不 emit per-run agent 生命周期事件（agent.stop 由 Agent.run 自行 emit）
    agent.hooks.emit.assert_not_awaited()


async def test_stop_before_start_is_noop():
    """未 start 直接 stop 不抛（_started 守卫）。"""
    runtime, *_ = _make_runtime(gateway=_FakeGateway("w"))
    await runtime.stop()  # 不抛


async def test_restart_after_stop():
    """start -> stop -> start -> stop：第二次 start 重建 scheduler task，gateway 复起。"""
    runtime, agent, reg, sched = _make_runtime(gateway=_FakeGateway("w"))
    await runtime.start()
    await _wait_for(lambda: sched.started)
    await runtime.stop()
    # 第二轮
    sched.started = False
    reg.get("w").started = False
    await runtime.start()
    await _wait_for(lambda: sched.started)
    assert reg.get("w").started is True
    assert runtime._scheduler_task is not None
    await runtime.stop()


async def test_agent_property_raises_before_start():
    runtime = AgentRuntime(config=MagicMock())  # 无 agent
    with pytest.raises(RuntimeError):
        _ = runtime.agent


async def test_start_without_scheduler_skips_scheduler():
    """ctx.scheduler 为 None（如 sync 构造未激活插件）时跳过 scheduler，不抛。"""
    reg = GatewayRegistry()
    reg.register(_FakeGateway("w"))
    agent = MagicMock()
    agent.run = AsyncMock(return_value="r")
    agent.hooks = MagicMock()
    agent.hooks.emit = AsyncMock()

    class _Ctx:
        pass

    ctx = _Ctx()
    ctx.scheduler = None
    ctx.gateway_registry = reg
    agent.plugin_ctx = ctx
    runtime = AgentRuntime(config=MagicMock(), agent=agent)
    await runtime.start()  # scheduler None，不抛
    assert reg.get("w").started is True
    await runtime.stop()
