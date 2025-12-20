"""路由"""

from __future__ import annotations

from .auth import router as auth_router
from .cookies import router as cookies_router

__all__ = ["auth_router", "cookies_router"]
