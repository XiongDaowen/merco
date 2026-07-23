"""WebhookGateway - FastAPI/uvicorn 参考网关适配器（同步请求/响应模型）。"""
from __future__ import annotations

import asyncio
import logging

from fastapi import FastAPI, Request

from merco.gateway.base import GatewayAdapter

logger = logging.getLogger("merco.gateway.webhook")


class WebhookGateway(GatewayAdapter):
    """POST {path} 收 {chat_id, message} -> message_handler -> {reply}。

    ``port=0`` 让 OS 分配空闲端口，启动后 ``actual_port`` 可读。
    ``send_message`` 配 ``outbound_url`` 时 POST 出站，否则 no-op（webhook 场景
    reply 已在 HTTP 响应里，满足 ABC 契约）。
    """

    name = "webhook"

    def __init__(self, *, host: str = "127.0.0.1", port: int = 0,
                 path: str = "/message", outbound_url: str | None = None):
        super().__init__()
        self.host = host
        self.port = port
        self.path = path
        self.outbound_url = outbound_url
        self._server = None
        self._serve_task: asyncio.Task | None = None
        self.actual_port: int | None = None

    async def start(self) -> None:
        import uvicorn

        app = FastAPI()
        gateway = self

        @app.post(self.path)
        async def _handle(request: Request):
            payload = await request.json()
            chat_id = payload.get("chat_id", "")
            message = payload.get("message", "")
            if gateway._message_handler is None:
                return {"reply": "", "error": "no handler bound"}
            reply = await gateway._message_handler(chat_id, message)
            return {"reply": reply}

        config = uvicorn.Config(app, host=self.host, port=self.port,
                                log_level="warning")
        self._server = uvicorn.Server(config)
        self._serve_task = asyncio.create_task(self._server.serve())
        # 等启动绑定端口（serve() 会在 started=True 后进 main_loop）
        while not self._server.started:
            if self._serve_task.done():
                self._serve_task.result()  # serve() 启动前退出 -> 抛其异常
            await asyncio.sleep(0.01)
        servers = self._server.servers or []
        socks = servers[0].sockets if servers else []
        self.actual_port = socks[0].getsockname()[1] if socks else self.port
        logger.info("WebhookGateway listening on %s:%s%s",
                    self.host, self.actual_port, self.path)

    async def stop(self) -> None:
        if self._server is not None:
            self._server.should_exit = True
        if self._serve_task is not None:
            try:
                await self._serve_task
            except Exception:
                logger.debug("WebhookGateway serve_task ended", exc_info=True)
            self._serve_task = None
        self._server = None

    async def send_message(self, chat_id: str, message: str) -> None:
        if not self.outbound_url:
            logger.debug("WebhookGateway.send_message no outbound_url; no-op (chat_id=%s)", chat_id)
            return
        import httpx
        async with httpx.AsyncClient() as client:
            await client.post(self.outbound_url,
                              json={"chat_id": chat_id, "message": message})
