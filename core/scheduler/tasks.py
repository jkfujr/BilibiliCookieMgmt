from __future__ import annotations

"""
后台调度任务: 
- 根据配置周期性执行 Cookie 健康检查与刷新
- 支持应用启动/停止的安全启停
"""

import asyncio
import logging
from typing import List, Optional

from fastapi import FastAPI

from ..services.cookie_service import CookieService
from ..infrastructure.repositories.cookie_repository import MANAGED_KEY
from ..config.loader import AppConfig


logger = logging.getLogger(__name__)


class AppScheduler:
    def __init__(self, service: CookieService, config: AppConfig):
        self.service = service
        self.config = config
        self._tasks: List[asyncio.Task] = []
        self._stopping = asyncio.Event()

    async def start(self, app: FastAPI) -> None:
        """根据配置启动后台任务。"""
        self._stopping.clear()
        if self.config.scheduler.cookie_check.enable:
            logger.info("启动 Cookie 检查任务")
            t = asyncio.create_task(self._loop_cookie_check())
            self._tasks.append(t)
        if self.config.scheduler.cookie_refresh.enable:
            logger.info("启动 Cookie 刷新任务")
            t = asyncio.create_task(self._loop_cookie_refresh())
            self._tasks.append(t)
        app.state.scheduler = self

    async def stop(self) -> None:
        """请求停止并取消所有任务。"""
        logger.info("停止所有调度任务...")
        self._stopping.set()
        for t in self._tasks:
            t.cancel()
            try:
                await t
            except asyncio.CancelledError:
                pass
        self._tasks.clear()
        logger.info("调度任务已停止")

    async def _loop_cookie_check(self) -> None:
        interval = max(1, int(self.config.scheduler.cookie_check.interval_seconds))
        logger.info(f"Cookie 检查循环已启动, 间隔: {interval}秒")
        while not self._stopping.is_set():
            try:
                # 遍历所有 cookie 执行检查
                items = await self.service.list_cookies()
                if items:
                    logger.info(f"开始检查 {len(items)} 个 Cookie")
                for doc in items:
                    info = doc.get(MANAGED_KEY, {}) if isinstance(doc.get(MANAGED_KEY), dict) else {}
                    dede_user_id = info.get("DedeUserID")
                    if dede_user_id:
                        await self.service.check_cookie(dede_user_id)
            except Exception as e:
                logger.error(f"Cookie 检查循环异常: {e}", exc_info=True)
            await asyncio.sleep(interval)

    async def _loop_cookie_refresh(self) -> None:
        interval = max(60, int(self.config.scheduler.cookie_refresh.interval_seconds))
        logger.info(f"Cookie 刷新循环已启动, 间隔: {interval}秒")
        while not self._stopping.is_set():
            try:
                # 基于上次刷新时间与配置间隔执行刷新
                items = await self.service.list_cookies()
                from datetime import datetime, timedelta
                threshold = timedelta(seconds=interval)
                for doc in items:
                    info = doc.get(MANAGED_KEY, {}) if isinstance(doc.get(MANAGED_KEY), dict) else {}
                    dede_user_id = info.get("DedeUserID")
                    last_refresh_iso = info.get("last_refresh_time")
                    try:
                        last_refresh = datetime.fromisoformat(last_refresh_iso) if last_refresh_iso else None
                    except Exception:
                        last_refresh = None
                    need_refresh = False
                    if last_refresh is None:
                        need_refresh = True
                    else:
                        need_refresh = (datetime.now() - last_refresh) >= threshold
                    if dede_user_id and need_refresh:
                        logger.info(f"触发自动刷新: {dede_user_id}")
                        await self.service.refresh_cookie(dede_user_id)
            except Exception as e:
                logger.error(f"Cookie 刷新循环异常: {e}", exc_info=True)
            await asyncio.sleep(interval)