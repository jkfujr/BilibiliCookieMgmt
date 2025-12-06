from __future__ import annotations

"""
程序入口: 
- 加载配置(new_code/config.yaml)
- 构建依赖(仓库与服务)
- 初始化 FastAPI 并挂载路由

运行: 
  python new_code/main.py
或: 
  uvicorn new_code.main:app --reload --host 0.0.0.0 --port 18000
"""

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path

# 修改为绝对导入, 以便从 new_code 目录直接运行 main.py
from core.config.loader import load_config
from core.infrastructure.repositories.cookie_repository import CookieRepository
from core.services.cookie_service import CookieService
from core.infrastructure.bilibili_client import BilibiliClient
from core.api.routes.cookies import router as cookies_router
from core.api.routes.auth import router as auth_router
from core.infrastructure.notifications import NoopNotificationService
from core.infrastructure.notifications.gotify import GotifyNotificationService
from core.scheduler.tasks import AppScheduler


def create_app() -> FastAPI:
    app = FastAPI(title="BilibiliCookieMgmt v2 API", version="2.0.0")

    # 加载配置
    config = load_config()
    app.state.config = config
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
    app.state.cookie_service = service

    # 路由
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

    # 启动调度器
    scheduler = AppScheduler(service=service, config=config)

    @app.on_event("startup")
    async def _on_startup():
        await scheduler.start(app)

    @app.on_event("shutdown")
    async def _on_shutdown():
        await scheduler.stop()
        # 关闭通知客户端(如有)
        try:
            if hasattr(notification, "aclose"):
                await notification.aclose()  # type: ignore
        except Exception:
            pass
        try:
            await bilibili_client.aclose()
        except Exception:
            pass

    return app


app = create_app()


if __name__ == "__main__":
    cfg = app.state.config
    uvicorn.run(app, host=cfg.host, port=cfg.port)