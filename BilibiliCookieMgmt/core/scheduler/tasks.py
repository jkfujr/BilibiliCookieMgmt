from __future__ import annotations

"""
后台调度任务: 
- 根据配置周期性执行 Cookie 健康检查与刷新
- 支持应用启动/停止的安全启停
"""

import asyncio
import contextlib
import logging
from typing import List, Optional

from fastapi import FastAPI

from ..services.task_service import TaskService
from ..config.loader import AppConfig


logger = logging.getLogger(__name__)


class AppScheduler:
    def __init__(self, task_service: TaskService, config: AppConfig):
        self.task_service = task_service
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
        if self.config.bili.bili_ticket_enabled:
            logger.info("启动 bili_ticket 刷新任务")
            t = asyncio.create_task(self._loop_bili_ticket_refresh())
            self._tasks.append(t)
        if self.config.bili.risk_control_enabled:
            logger.info("启动风控检测任务")
            t = asyncio.create_task(self._loop_risk_control_check())
            self._tasks.append(t)
        app.state.scheduler = self

    async def stop(self) -> None:
        """请求停止并取消所有任务。"""
        logger.info("停止所有调度任务...")
        self._stopping.set()
        _, pending = await asyncio.wait(self._tasks, timeout=0.25) if self._tasks else (set(), set())
        for t in pending:
            t.cancel()
        for t in self._tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await t
        self._tasks.clear()
        logger.info("调度任务已停止")

    async def _loop_cookie_check(self) -> None:
        interval = max(1, int(self.config.scheduler.cookie_check.interval_seconds))
        logger.info(f"Cookie 检查循环已启动, 间隔: {interval}秒")
        while not self._stopping.is_set():
            try:
                task = await self.task_service.create_scheduled_cookie_check()
                if task:
                    await self.task_service.wait(task["id"])
            except Exception as e:
                logger.error(f"Cookie 检查循环异常: {e}", exc_info=True)
            await asyncio.sleep(interval)

    async def _loop_bili_ticket_refresh(self) -> None:
        interval = max(60, int(self.config.scheduler.bili_ticket_refresh.interval_seconds))
        logger.info(f"bili_ticket 刷新循环已启动, 间隔: {interval}秒")
        while not self._stopping.is_set():
            try:
                task = await self.task_service.create_scheduled_ticket_refresh()
                if task:
                    await self.task_service.wait(task["id"])
            except Exception as e:
                logger.error(f"bili_ticket 刷新循环异常: {e}", exc_info=True)
            await asyncio.sleep(interval)

    async def _loop_cookie_refresh(self) -> None:
        threshold = max(60, int(self.config.scheduler.cookie_refresh.interval_seconds))
        scan_interval = max(60, int(self.config.scheduler.cookie_refresh.scan_interval_seconds))
        logger.info(f"Cookie 刷新循环已启动, 扫描间隔: {scan_interval}秒, 临期阈值: {threshold}秒")
        while not self._stopping.is_set():
            try:
                task = await self.task_service.create_scheduled_cookie_refresh(threshold)
                if task:
                    await self.task_service.wait(task["id"])
            except Exception as e:
                logger.error(f"Cookie 刷新循环异常: {e}", exc_info=True)
            await asyncio.sleep(scan_interval)

    async def _loop_risk_control_check(self) -> None:
        interval = max(60, int(self.config.scheduler.risk_control_check.interval_seconds))
        logger.info(f"风控检测循环已启动, 间隔: {interval}秒")
        while not self._stopping.is_set():
            try:
                task = await self.task_service.create_scheduled_risk_check()
                if task:
                    await self.task_service.wait(task["id"])
            except Exception as e:
                logger.error(f"风控检测循环异常: {e}", exc_info=True)
            await asyncio.sleep(interval)
