from __future__ import annotations

"""
设置路由。
"""

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request

from ...services.settings_service import SettingsService
from ...utils.security import require_api_token


router = APIRouter(prefix="/settings", tags=["settings"], dependencies=[Depends(require_api_token)])


@router.get("/")
async def get_settings(request: Request):
    service = SettingsService(request.app)
    return service.get_settings()


@router.put("/")
async def update_settings(payload: Dict[str, Any], request: Request):
    service = SettingsService(request.app)
    try:
        return await service.update_settings(payload)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
