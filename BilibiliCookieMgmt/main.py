from __future__ import annotations

"""
程序入口: 
- 加载配置(data/config.json)
- 构建依赖(仓库与服务)
- 初始化 FastAPI 并挂载路由

运行: 
  python main.py
或: 
  uvicorn main:app --reload --host 0.0.0.0 --port 18000
"""

import uvicorn, logging
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path
from contextlib import asynccontextmanager

from core.api.routes import auth_router, cookies_router, settings_router
from core.config import load_config
from core.infrastructure import BilibiliClient
from core.infrastructure.repositories import CookieRepository
from core.scheduler import AppScheduler
from core.services import CookieService
from core.services.settings_service import build_notification_service
from core.utils import setup_logging

def create_app() -> FastAPI:
    # 初始化日志
    setup_logging()
    logger = logging.getLogger(__name__)

    # 加载配置
    config = load_config()
    logger.info(f"配置加载完成, 端口: {config.port}")

    repository = CookieRepository(
        base_dir=config.storage.cookie_dir,
        bili_ticket_enabled=config.bili.bili_ticket_enabled
    )
    notification = build_notification_service(config)
    bilibili_client = BilibiliClient()
    service = CookieService(repository=repository, config=config, notification=notification, bilibili_client=bilibili_client)

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
            current_scheduler = getattr(app.state, "scheduler", scheduler)
            await current_scheduler.stop()
            try:
                current_notification = getattr(app.state, "notification", notification)
                if hasattr(current_notification, "aclose"):
                    await current_notification.aclose()  # type: ignore
            except Exception:
                pass
            try:
                await bilibili_client.aclose()
            except Exception:
                pass

    app = FastAPI(title="BilibiliCookieMgmt v2 API", version="2.0.0", lifespan=lifespan)
    app.state.config = config
    app.state.cookie_service = service
    app.state.notification = notification

    app.include_router(cookies_router, prefix="/api/v1")
    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(settings_router, prefix="/api/v1")

    @app.get("/api/v1/health", tags=["health"])
    async def health_check():
        return {"status": "ok"}

    # 主页
    base_dir = Path(__file__).resolve().parent
    static_dir = base_dir / "static"
    assets_dir = static_dir / "assets"
    index_file = static_dir / "index.html"

    if static_dir.exists() and static_dir.is_dir():
        if assets_dir.exists() and assets_dir.is_dir():
            app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
        root_message = "Backend is running. Frontend static files not found."
    else:
        root_message = "Backend is running. Frontend static files directory not found."

    @app.get("/", include_in_schema=False)
    async def index_page():
        if index_file.exists():
            return FileResponse(str(index_file))
        return {"status": "ok", "message": root_message}

    return app


app = create_app()


if __name__ == "__main__":
    cfg = app.state.config
    uvicorn.run(app, host=cfg.host, port=cfg.port)
