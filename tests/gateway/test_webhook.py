"""WebhookGateway 测试：start/port=0/POST->handler->{reply}/stop/send_message。"""

import httpx

from merco.gateway.webhook import WebhookGateway


async def _async_none():
    return ""


async def test_post_returns_handler_reply():
    """POST /message {chat_id, message} -> {reply}（同步请求/响应模型）。"""
    gw = WebhookGateway()

    async def handler(chat_id, message):
        return f"echo:{chat_id}:{message}"

    gw.set_message_handler(handler)
    await gw.start()
    try:
        port = gw.actual_port
        assert port and port > 0
        async with httpx.AsyncClient() as c:
            r = await c.post(
                f"http://127.0.0.1:{port}/message",
                json={"chat_id": "c1", "message": "hi"},
            )
        assert r.status_code == 200
        assert r.json() == {"reply": "echo:c1:hi"}
    finally:
        await gw.stop()


async def test_port_zero_assigns_real_port():
    gw = WebhookGateway(port=0)
    gw.set_message_handler(lambda cid, msg: _async_none())
    await gw.start()
    try:
        assert gw.actual_port != 0
        assert gw.actual_port > 0
    finally:
        await gw.stop()


async def test_send_message_no_outbound_url_is_noop():
    """无 outbound_url 时 send_message no-op（webhook reply 已在 HTTP 响应里）。"""
    gw = WebhookGateway()
    await gw.send_message("c1", "hi")  # 不抛、不连网


async def test_send_message_with_outbound_url_posts():
    """配 outbound_url 时 POST 出站。"""
    posted = []

    async def outbound_handler(chat_id, message):
        posted.append((chat_id, message))
        return ""

    async def handler(chat_id, message):
        return ""

    gw = WebhookGateway()
    gw.set_message_handler(handler)
    await gw.start()
    try:
        gw_out = WebhookGateway()
        gw_out.set_message_handler(outbound_handler)
        await gw_out.start()
        try:
            gw.outbound_url = f"http://127.0.0.1:{gw_out.actual_port}/message"
            await gw.send_message("c1", "out")
            assert posted == [("c1", "out")]
        finally:
            await gw_out.stop()
    finally:
        await gw.stop()


async def test_post_without_handler_returns_error_field():
    """未绑 handler 时 POST 返回 200 + error 字段（registry 正常驱动时不会走到）。"""
    gw = WebhookGateway()
    await gw.start()
    try:
        port = gw.actual_port
        async with httpx.AsyncClient() as c:
            r = await c.post(
                f"http://127.0.0.1:{port}/message",
                json={"chat_id": "c1", "message": "hi"},
            )
        assert r.status_code == 200
        assert r.json()["reply"] == ""
        assert "error" in r.json()
    finally:
        await gw.stop()


async def test_start_idempotent_after_stop():
    """stop 后 server 干净退出（serve_task 完成，状态清空）；重复 stop 不抛。"""
    gw = WebhookGateway()
    gw.set_message_handler(lambda cid, msg: _async_none())
    await gw.start()
    await gw.stop()
    # stop 清空了运行态
    assert gw._server is None
    assert gw._serve_task is None
    # 再 stop 不抛
    await gw.stop()
    assert gw._server is None
