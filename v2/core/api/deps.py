from __future__ import annotations

"""API依赖"""

from fastapi import Request


def get_config(request: Request):
    return request.app.state.config


def get_cookie_service(request: Request):
    return request.app.state.cookie_service