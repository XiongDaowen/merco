"""OpenMercury Web GUI server."""

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
import uvicorn

app = FastAPI(title="OpenMercury", version="0.1.0")


@app.get("/")
async def root():
    return {"message": "OpenMercury Web GUI", "version": "0.1.0"}


@app.get("/health")
async def health():
    return {"status": "ok"}


def main():
    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
