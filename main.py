import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager

from core.config import get_config_manager
from core.scheduler import run as scheduler_run
from core.routes.auth import router as auth_router
from core.routes.cookie import router as cookie_router
from core.routes.main import router as main_router

@asynccontextmanager
async def run(app: FastAPI):
    # 启动调度
    async with scheduler_run(app):
        yield


# 初始化配置
config_manager = get_config_manager()
config_manager.initialize()
app_config = config_manager.config

# fastapi
app = FastAPI(lifespan=run)
app.mount("/static", StaticFiles(directory="static"), name="static")

# 路由
app.include_router(auth_router)
app.include_router(cookie_router)
app.include_router(main_router)

# 启动
if __name__ == "__main__":
    uvicorn.run(app, host=app_config.server.host, port=app_config.server.port)
