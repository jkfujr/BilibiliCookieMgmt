from __future__ import annotations

"""API依赖"""

from fastapi import Request


def get_config(request: Request):
    return request.app.state.config


def get_cookie_service(request: Request):
    return request.app.state.cookie_service


def get_task_service(request: Request):
    service = getattr(request.app.state, "task_service", None)
    if service is None:
        raise RuntimeError("任务服务尚未启动")
    return service
