from __future__ import annotations

"""
扫码登录(TV 登录)相关路由: 
- GET /auth/tv/qrcode  生成二维码(返回 auth_code 与 qrcode_url)
- GET /auth/tv/poll    轮询扫码结果(成功后自动保存原始响应为 Cookie)

说明: 
- 仅做 HTTP 输入输出与简单的字段整形；业务写在 CookieService/BilibiliClient。
"""

from typing import Any, Dict
from fastapi import APIRouter, Depends, HTTPException, Query

from ..deps import get_cookie_service
from ...utils.security import require_api_token

router = APIRouter(prefix="/auth", tags=["auth"], dependencies=[Depends(require_api_token)])


@router.get("/tv/qrcode")
async def tv_generate_qrcode(service = Depends(get_cookie_service)):
    """
    生成 TV 扫码登录二维码。
    返回: {"auth_code": str, "qrcode_url": str}
    """
    client = getattr(service, "client", None)
    if client is None:
        raise HTTPException(status_code=500, detail="Bilibili 客户端未初始化")

    resp: Dict[str, Any] = await client.generate_qrcode()
    if resp.get("code") != 0:
        raise HTTPException(status_code=502, detail=resp.get("message", "生成二维码失败"))

    data = resp.get("data", {})
    auth_code = data.get("auth_code")
    qrcode_url = data.get("qrcode_url") or data.get("url")
    if not auth_code or not qrcode_url:
        raise HTTPException(status_code=500, detail="响应缺少 auth_code 或 qrcode_url")

    return {"auth_code": auth_code, "qrcode_url": qrcode_url}


@router.get("/tv/poll")
async def tv_poll_status(auth_code: str = Query(..., description="生成二维码返回的 auth_code"),
                         service = Depends(get_cookie_service)):
    """
    轮询 TV 扫码状态: 
    - code == 0 时: 登录成功, 自动保存原始响应(data)为 Cookie 文档并返回保存后的文档
    - 其它状态: 返回 {code, message}
    """
    client = getattr(service, "client", None)
    if client is None:
        raise HTTPException(status_code=500, detail="Bilibili 客户端未初始化")

    resp: Dict[str, Any] = await client.poll_qrcode_status(auth_code)
    code = resp.get("code")

    if code == 0:
        data: Dict[str, Any] = resp.get("data", {})
        try:
            saved = await service.create_from_raw(data)

            try:
                info = saved.get("managed", {}) if isinstance(saved.get("managed"), dict) else {}
                dede_user_id = info.get("DedeUserID")
                if dede_user_id:
                    enriched = await service.enrich_after_create(dede_user_id)
                    return enriched or saved
            except Exception:
                return saved

            return saved
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"保存失败: {e}")

    return {"code": code, "message": resp.get("message", "未知状态")}