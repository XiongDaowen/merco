"""E2E: webhook POST -> Runtime.handle_inbound -> agent.run -> HTTP reply.

复用 test_anthropic_agent_integration 的 _build_agent（sync 构造 + mock provider）
+ _final_text_response（合法终态响应，无 tool_calls，loop 一轮退出）。
手动注册 WebhookGateway（sync 构造未走插件激活），证明 Runtime 接线正确。
"""
from unittest.mock import AsyncMock

import httpx
import pytest

from merco.core.runtime import AgentRuntime
from merco.gateway.webhook import WebhookGateway
from tests.integration.test_anthropic_agent_integration import (
    _build_agent,
    _final_text_response,
    _quiet_console,
)


@pytest.mark.asyncio
async def test_webhook_post_through_runtime_returns_agent_reply(monkeypatch, tmp_path):
    """webhook POST -> Runtime.handle_inbound -> agent.run -> HTTP {reply: done}。"""
    _quiet_console(monkeypatch)
    agent, _ = _build_agent(monkeypatch, tmp_path, streaming=False)
    # mock provider 一轮终态响应（"done"），loop 立即退出
    agent.provider.client.messages.create = AsyncMock(return_value=_final_text_response())

    # 手动注册 WebhookGateway（sync 构造未激活 GatewayPlugin）
    agent.gateway_registry.register(WebhookGateway())

    runtime = AgentRuntime(config=agent.config, agent=agent)
    await runtime.start()
    try:
        port = runtime.gateway_registry.get("webhook").actual_port
        assert port and port > 0
        async with httpx.AsyncClient() as c:
            r = await c.post(
                f"http://127.0.0.1:{port}/message",
                json={"chat_id": "c1", "message": "hello"},
            )
        assert r.status_code == 200
        body = r.json()
        assert "reply" in body
        assert "done" in body["reply"], body
    finally:
        await runtime.stop()


@pytest.mark.asyncio
async def test_runtime_submit_drives_agent_loop(monkeypatch, tmp_path):
    """编程式 submit 也走 agent.run（与 webhook 同路径）。"""
    _quiet_console(monkeypatch)
    agent, _ = _build_agent(monkeypatch, tmp_path, streaming=False)
    agent.provider.client.messages.create = AsyncMock(return_value=_final_text_response())

    runtime = AgentRuntime(config=agent.config, agent=agent)
    await runtime.start()
    try:
        result = await runtime.submit("hello")
        assert "done" in result
    finally:
        await runtime.stop()
