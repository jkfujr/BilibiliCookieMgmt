import time, aiohttp
from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import JSONResponse

from core.auth import tvsign, USER_AGENT
from core.cookie import save_cookie, build_cookie_string, fetch_and_save_buvid, check_cookie
from core.logs import log

logger = log()
router = APIRouter()


# API TOKEN 验证
async def verify_api_token(token: str = Header(None)):
    from core.config import get_config_manager
    config_manager = get_config_manager()
    app_config = config_manager.config
    
    if app_config.server.api_token:
        if token != app_config.server.api_token:
            raise HTTPException(status_code=401, detail="无效或缺失的 API Token")


# 生成二维码
@router.get("/api/passport-login/web/qrcode/generate")
async def generate_qr(token: str = Header(None)):
    await verify_api_token(token)
    url = "https://passport.bilibili.com/x/passport-tv-login/qrcode/auth_code"
    params = tvsign({"local_id": "0", "ts": int(time.time())})
    headers = {"User-Agent": USER_AGENT}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, params=params, headers=headers) as response:
                data = await response.json()
        return {"code": data["code"], "data": data["data"]}
    except aiohttp.ClientError as e:
        raise HTTPException(status_code=500, detail=str(e))


# 轮询扫码状态
@router.get("/api/passport-login/web/qrcode/poll")
async def poll_qr(auth_code: str, token: str = Header(None)):
    await verify_api_token(token)
    url = "https://passport.bilibili.com/x/passport-tv-login/qrcode/poll"
    params = tvsign({"auth_code": auth_code, "local_id": "0", "ts": int(time.time())})
    headers = {"User-Agent": USER_AGENT}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, params=params, headers=headers) as response:
                data = await response.json()
        # print(data)
        if data["code"] == 0:
            login_data = data["data"]
            save_cookie(login_data)
            
            # 扫码成功执行检查
            DedeUserID = ""
            for cookie in login_data["cookie_info"]["cookies"]:
                if cookie["name"] == "DedeUserID":
                    DedeUserID = cookie["value"]
                    break
            
            if DedeUserID:
                logger.info(f"[登录] 用户 {DedeUserID} 扫码登录成功，正在获取 buvid 和检查 Cookie 有效性...")
                cookies = login_data["cookie_info"]["cookies"]
                cookie_str = build_cookie_string(cookies)
                await fetch_and_save_buvid(DedeUserID, cookie_str)

                # 检查 Cookie 有效性
                await check_cookie(DedeUserID)

            return JSONResponse(
                content={"code": 0, "message": "扫码成功", "data": login_data}
            )
        elif data["code"] == -3:
            raise HTTPException(status_code=500, detail="API校验密匙错误")
        elif data["code"] == -400:
            raise HTTPException(status_code=500, detail="请求错误")
        elif data["code"] == 86038:
            return JSONResponse(content={"code": 86038, "message": "二维码已失效"})
        elif data["code"] == 86090:
            return JSONResponse(content={"code": 86090, "message": "等待扫码"})
        else:
            raise HTTPException(status_code=500, detail="未知错误")
    except aiohttp.ClientError as e:
        raise HTTPException(status_code=500, detail=str(e))