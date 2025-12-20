from __future__ import annotations

"""
Gotify 通知服务实现: 
- 依赖 httpx 异步客户端
- 发送简单文本消息到指定 Gotify 实例
"""

import httpx
from typing import Optional

from . import NotificationService


class GotifyNotificationService(NotificationService):
    def __init__(self, url: str, token: str, default_title: str = "BilibiliCookieMgmt", default_priority: int = 5):
        if not url.endswith("/message"):
            url = url.rstrip("/") + "/message"
        self.url = url
        self.token = token
        self.default_title = default_title
        self.default_priority = default_priority
        self._client = httpx.AsyncClient(timeout=10.0)

    async def send(self, title: str, message: str, priority: int = 5) -> None:
        payload = {
            "title": title or self.default_title,
            "message": message,
            "priority": int(priority if priority is not None else self.default_priority),
        }
        headers = {"X-Gotify-Key": self.token}
        try:
            resp = await self._client.post(self.url, json=payload, headers=headers)
            resp.raise_for_status()
        except Exception:
            return None

    async def aclose(self) -> None:
        await self._client.aclose()