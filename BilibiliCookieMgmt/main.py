from __future__ import annotations

"""
程序入口: 
- 加载配置(config.yaml)
- 构建依赖(仓库与服务)
- 初始化 FastAPI 并挂载路由

运行: 
  python main.py
或: 
  uvicorn new_code.main:app --reload --host 0.0.0.0 --port 18000
"""

import uvicorn, logging
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path
from contextlib import asynccontextmanager

from core.api.routes import auth_router, cookies_router
from core.config import load_config
from core.infrastructure import BilibiliClient
from core.infrastructure.notifications import GotifyNotificationService, NoopNotificationService
from core.infrastructure.repositories import CookieRepository
from core.scheduler import AppScheduler
from core.services import CookieService
from core.utils import setup_logging

def create_app() -> FastAPI:
    # 初始化日志
    setup_logging()
    logger = logging.getLogger(__name__)

    # 加载配置
    config = load_config()
    logger.info(f"配置加载完成, 端口: {config.port}")

    repository = CookieRepository(base_dir=config.storage.cookie_dir)
    # 通知服务
    if config.gotify.enable and config.gotify.url and config.gotify.token:
        notification = GotifyNotificationService(
            url=config.gotify.url,
            token=config.gotify.token,
            default_title=config.gotify.title,
            default_priority=config.gotify.priority,
        )
    else:
        notification = NoopNotificationService()

    bilibili_client = BilibiliClient()
    service = CookieService(repository=repository, notification=notification, bilibili_client=bilibili_client)

    # 路由
    scheduler = AppScheduler(service=service, config=config)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        logger.info("应用程序启动中...")
        await scheduler.start(app)
        logger.info("调度器已启动")
        try:
            yield
        finally:
            logger.info("应用程序正在关闭...")
            await scheduler.stop()
            try:
                if hasattr(notification, "aclose"):
                    await notification.aclose()  # type: ignore
            except Exception:
                pass
            try:
                await bilibili_client.aclose()
            except Exception:
                pass

    app = FastAPI(title="BilibiliCookieMgmt v2 API", version="2.0.0", lifespan=lifespan)
    app.state.config = config
    app.state.cookie_service = service

    app.include_router(cookies_router, prefix="/api/v1")
    app.include_router(auth_router, prefix="/api/v1")

    @app.get("/api/v1/health", tags=["health"])
    async def health_check():
        return {"status": "ok"}

    # 主页
    base_dir = Path(__file__).resolve().parent
    static_dir = base_dir / "static"
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    @app.get("/", include_in_schema=False)
    async def index_page():
        return FileResponse(str(static_dir / "index.html"))

    return app


app = create_app()


if __name__ == "__main__":
    cfg = app.state.config
    uvicorn.run(app, host=cfg.host, port=cfg.port)
