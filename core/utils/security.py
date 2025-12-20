from __future__ import annotations

"""
接口鉴权工具: Bearer Token 验证(可开关)。
鉴权逻辑: 
- 若配置中 API_TOKEN.enable 为 False, 则直接放行
- 若为 True, 则要求请求头 Authorization: Bearer <token>
"""

from fastapi import Request, HTTPException


def require_api_token(request: Request):
    cfg = request.app.state.config
    if not cfg.api_token.enable:
        return  # 不启用鉴权, 直接放行

    auth = request.headers.get("Authorization", "")
    prefix = "Bearer "
    if not auth.startswith(prefix):
        raise HTTPException(status_code=401, detail="缺少或错误的 Authorization 头")

    token = auth[len(prefix):].strip()
    if token != cfg.api_token.token:
        raise HTTPException(status_code=401, detail="无效的 Token")