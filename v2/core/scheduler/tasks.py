from __future__ import annotations

"""
后台调度任务: 
- 根据配置周期性执行 Cookie 健康检查与刷新
- 支持应用启动/停止的安全启停
"""

import asyncio
from typing import List, Optional

from fastapi import FastAPI

from ..services.cookie_service import CookieService
from ..infrastructure.repositories.cookie_repository import MANAGED_KEY
from ..config.loader import AppConfig


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
            t = asyncio.create_task(self._loop_cookie_check())
            self._tasks.append(t)
        if self.config.scheduler.cookie_refresh.enable:
            t = asyncio.create_task(self._loop_cookie_refresh())
            self._tasks.append(t)
        app.state.scheduler = self

    async def stop(self) -> None:
        """请求停止并取消所有任务。"""
        self._stopping.set()
        for t in self._tasks:
            t.cancel()
            try:
                await t
            except asyncio.CancelledError:
                pass
        self._tasks.clear()

    async def _loop_cookie_check(self) -> None:
        interval = max(1, int(self.config.scheduler.cookie_check.interval_seconds))
        while not self._stopping.is_set():
            try:
                # 遍历所有 cookie 执行检查
                items = await self.service.list_cookies()
                for doc in items:
                    info = doc.get(MANAGED_KEY, {}) if isinstance(doc.get(MANAGED_KEY), dict) else {}
                    dede_user_id = info.get("DedeUserID")
                    if dede_user_id:
                        await self.service.check_cookie(dede_user_id)
            except Exception:
                # 静默忽略单次任务错误(可扩展为日志)
                pass
            await asyncio.sleep(interval)

    async def _loop_cookie_refresh(self) -> None:
        interval = max(60, int(self.config.scheduler.cookie_refresh.interval_seconds))
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
                        await self.service.refresh_cookie(dede_user_id)
            except Exception:
                pass
            await asyncio.sleep(interval)