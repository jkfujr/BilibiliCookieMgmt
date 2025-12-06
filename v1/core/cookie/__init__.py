from typing import Optional, Dict, Any

__all__ = [
    'read_cookie',
    'save_cookie',
    'get_cookie_file_path',
    'check_cookie',
    'check_all_cookies',
    'check_cookie_validity',
    'refresh_cookie',
    'refresh_expired_cookies',
    'build_cookie_string',
    'fetch_buvid',
    'fetch_and_save_buvid',
    'update_buvid_if_missing'
]

# cookie管理
from .manager import get_cookie_file_path, read_cookie, save_cookie, refresh_cookie

# buvid
from .buvid import build_cookie_string, fetch_buvid, fetch_and_save_buvid, update_buvid_if_missing

# 健康检查
from .health import check_cookie, check_cookie_validity, check_all_cookies, refresh_expired_cookies

def __getattr__(name: str) -> Any:
    if name == 'COOKIE_FOLDER':
        from .manager import COOKIE_FOLDER
        return COOKIE_FOLDER
    raise AttributeError(f"模块 '{__name__}' 没有属性 '{name}'")