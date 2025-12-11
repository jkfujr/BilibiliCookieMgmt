from __future__ import annotations

"""
Cookie 相关路由
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Body
from typing import List, Optional

from ..deps import get_cookie_service
from ...utils.security import require_api_token

router = APIRouter(prefix="/cookies", tags=["cookies"], dependencies=[Depends(require_api_token)])


@router.get("/random")
async def get_random_cookie(format: str = "simple", service = Depends(get_cookie_service)):
    result = await service.get_random_cookie(fmt=format)
    if not result:
        raise HTTPException(status_code=404, detail="没有可用的 Cookie")
    return result


@router.get("/")
async def list_cookies(service = Depends(get_cookie_service)):
    """返回所有 Cookie 的完整文档(原始与管理信息)。"""
    return await service.list_cookies()


@router.get("/{DedeUserID}")
async def get_cookie(DedeUserID: str, service = Depends(get_cookie_service)):
    doc = await service.get_cookie(DedeUserID)
    if not doc:
        raise HTTPException(status_code=404, detail="Cookie 不存在")
    return doc


@router.delete("/{DedeUserID}")
async def delete_cookie(DedeUserID: str, service = Depends(get_cookie_service)):
    ok = await service.delete_cookie(DedeUserID)
    if not ok:
        raise HTTPException(status_code=404, detail="Cookie 不存在")
    return {"deleted": True, "DedeUserID": DedeUserID}



@router.post("/test")
async def test_cookie(cookie: str = Body(..., embed=True, description="Cookie 请求头字符串, 如 SESSDATA=...; bili_jct=...; DedeUserID=..."),
                      service = Depends(get_cookie_service)):
    """测试任意 Cookie 字符串是否有效。"""
    return await service.test_cookie(cookie)


@router.post("/check")
async def check_cookies(
    all: bool = Query(False, description="是否对全部 Cookie 执行检查"),
    ids: Optional[List[str]] = Body(None, embed=True, description="要检查的 DedeUserID 列表"),
    service = Depends(get_cookie_service),
):
    """
    统一的批量检查接口: 
    - all=true: 检查全部启用的 Cookie
    - 提供 ids: 检查指定 ID 列表
    返回执行摘要与明细列表。
    """
    return await service.check_cookies(ids=ids, all=all)


@router.post("/refresh")
async def refresh_cookies(
    all: bool = Query(False, description="是否对全部 Cookie 执行刷新"),
    ids: Optional[List[str]] = Body(None, embed=True, description="要刷新的 DedeUserID 列表"),
    service = Depends(get_cookie_service),
):
    """
    统一的批量刷新接口: 
    - all=true: 刷新全部启用的 Cookie
    - 提供 ids: 刷新指定 ID 列表
    返回执行摘要与明细列表。
    """
    return await service.refresh_cookies(ids=ids, all=all)


@router.patch("/{DedeUserID}/enabled")
async def set_enabled(DedeUserID: str, is_enabled: bool = Body(..., embed=True, description="启用或禁用该 Cookie"),
                      service = Depends(get_cookie_service)):
    """
    设置启用/禁用状态。
    注意: 该状态仅影响随机 Cookie 选择(/cookies/random)。检查与刷新不受此状态影响。
    """
    doc = await service.set_enabled(DedeUserID, is_enabled)
    if not doc:
        raise HTTPException(status_code=404, detail="Cookie 不存在")
    return doc
