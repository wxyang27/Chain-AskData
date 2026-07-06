from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.routes import router as api_router
from app.web.routes import router as web_router


def create_app() -> FastAPI:
    """创建 FastAPI 应用实例。"""

    app = FastAPI(
        title="Chain-AskData",
        description="新氧连锁经管自然语言取数 MVP",
        version="0.1.0",
    )
    app.include_router(api_router, prefix="/api")
    app.include_router(web_router)
    app.mount("/static", StaticFiles(directory="static"), name="static")
    return app


app = create_app()
