from .auth import router as auth_router
from .cookie import router as cookie_router
from .main import router as main_router

__all__ = ["auth_router", "cookie_router", "main_router"]