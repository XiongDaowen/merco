"""FastAPI Web 应用"""

from fastapi import FastAPI


def create_app() -> FastAPI:
    """创建 FastAPI 应用"""
    app = FastAPI(
        title="Mercury Code",
        description="AI 驱动的自改进软件开发平台",
        version="0.1.0",
    )

    @app.get("/")
    async def root():
        return {"message": "Mercury Code API", "version": "0.1.0"}

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.post("/chat")
    async def chat(message: str):
        # TODO: 集成 Agent 处理消息
        return {"response": "Chat endpoint - coming soon"}

    return app
