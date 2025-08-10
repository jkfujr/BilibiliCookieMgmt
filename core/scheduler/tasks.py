import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI

from core.logs import log, log_print
from core.cookie import check_all_cookies, refresh_expired_cookies

logger = log()


async def periodic_cookie_check():
    """定时-检查所有 Cookie"""
    from core.config import get_config_manager
    config_manager = get_config_manager()
    app_config = config_manager.config
    
    try:
        while True:
            logger.debug("[检查] 开始自动检查所有 Cookie 有效性...")
            try:
                await check_all_cookies()
            except Exception as e:
                log_print(f"[检查] 自动检查过程中出现错误: {e}", "ERROR")
            logger.debug(f"[检查] 下一次检查将在 {app_config.cookie.check_interval} 秒后进行。")
            await asyncio.sleep(app_config.cookie.check_interval)
    except asyncio.CancelledError:
        logger.debug("[检查] 自动 Cookie 检查已取消。")
        raise


async def periodic_cookie_refresh():
    """定时-刷新需要刷新的 Cookie"""
    try:
        while True:
            logger.debug("[刷新] 开始自动刷新需要更新的 Cookie...")
            try:
                await refresh_expired_cookies()
            except Exception as e:
                log_print(f"[刷新] 自动刷新过程中出现错误: {e}", "ERROR")
            await asyncio.sleep(24 * 60 * 60)
    except asyncio.CancelledError:
        logger.debug("[刷新] 自动 Cookie 刷新已取消。")
        raise


@asynccontextmanager
async def run(app: FastAPI):
    """启动函数"""
    from core.config import get_config_manager
    config_manager = get_config_manager()
    app_config = config_manager.config
    
    tasks = []
    if app_config.cookie.check_enabled:
        logger.debug(
            f"[检查] 自动 Cookie 检查已启用，检查间隔为 {app_config.cookie.check_interval} 秒。"
        )
        check_task = asyncio.create_task(periodic_cookie_check())
        tasks.append(check_task)
    else:
        logger.debug("[检查] 自动 Cookie 检查未启用。")

    if app_config.cookie.refresh_enabled:
        logger.debug(
            f"[刷新] 自动 Cookie 刷新已启用，刷新间隔为 {app_config.cookie.refresh_interval} 天。"
        )
        refresh_task = asyncio.create_task(periodic_cookie_refresh())
        tasks.append(refresh_task)
    else:
        logger.debug("[刷新] 自动 Cookie 刷新未启用。")

    yield

    for task in tasks:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass