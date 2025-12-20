from __future__ import annotations

"""
通知服务抽象与基础实现: 
- NotificationService: 抽象接口
- NoopNotificationService: 空实现(关闭通知时使用)
"""

from typing import Optional
from dataclasses import dataclass


@dataclass
class NotificationMessage:
    title: str
    message: str
    priority: int = 5


class NotificationService:
    async def send(self, title: str, message: str, priority: int = 5) -> None:
        """发送通知"""
        raise NotImplementedError


class NoopNotificationService(NotificationService):
    async def send(self, title: str, message: str, priority: int = 5) -> None:
        return None


from .gotify import GotifyNotificationService

__all__ = [
    "NotificationMessage",
    "NotificationService",
    "NoopNotificationService",
    "GotifyNotificationService",
]
