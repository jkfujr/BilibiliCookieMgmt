import os, json, random
from fastapi import APIRouter, Header, Query, Body, HTTPException
from fastapi.responses import JSONResponse

from core.cookie import read_cookie, get_cookie_file_path, refresh_cookie, check_cookie, check_all_cookies, check_cookie_validity, refresh_expired_cookies
from core.logs import log
from core.notifications.gotify import ez_push_gotify

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


# 获取Cookie信息
@router.get("/api/cookie")
async def get_cookies(DedeUserID: str = Query(None), token: str = Header(None)):
    from core.config import get_config_manager
    config_manager = get_config_manager()
    app_config = config_manager.config
    COOKIE_FOLDER = app_config.cookie.folder

    
    if DedeUserID:
        await verify_api_token(token)

        cookie_data = read_cookie(DedeUserID)
        if cookie_data:
            if "_cookiemgmt" in cookie_data:
                mgmt_data = cookie_data["_cookiemgmt"]
                cookie_data["cookie_valid"] = mgmt_data.get("cookie_valid")
                cookie_data["refresh_status"] = mgmt_data.get("refresh_status", "unknown")
                if mgmt_data.get("last_check_time"):
                    cookie_data["check_time"] = mgmt_data["last_check_time"]
                if mgmt_data.get("error_message"):
                    cookie_data["error_message"] = mgmt_data["error_message"]
            else:
                logger.warning(f"[API] 用户 {DedeUserID} 使用旧格式，建议等待自动刷新完成")
            return JSONResponse(content=cookie_data)
        else:
            raise HTTPException(status_code=404, detail="未找到指定的 Cookie 信息")
    else:
        cookies = []
        if os.path.exists(COOKIE_FOLDER):
            for filename in os.listdir(COOKIE_FOLDER):
                if filename.endswith(".json"):
                    file_path = os.path.join(COOKIE_FOLDER, filename)
                    try:
                        with open(file_path, "r", encoding="utf-8") as file:
                            file_content = file.read().strip()
                            if not file_content:
                                logger.warning(f"[读取] 文件 {filename} 为空，跳过")
                                continue
                            
                            cookie_data = json.loads(file_content)
                            DedeUserID = filename.replace(".json", "")
                            
                            if "_cookiemgmt" in cookie_data:
                                mgmt_data = cookie_data["_cookiemgmt"]
                                update_time = mgmt_data.get("update_time", 0)
                                cookie_valid = mgmt_data.get("cookie_valid")
                                check_time = mgmt_data.get("last_check_time")
                                refresh_status = mgmt_data.get("refresh_status", "unknown")
                                
                                expires_in = cookie_data["token_info"].get("expires_in", 0)
                                expire_timestamp = update_time + int(expires_in) * 1000
                                
                                cookies.append(
                                    {
                                        "DedeUserID": DedeUserID,
                                        "update_time": update_time,
                                        "expire_time": expire_timestamp,
                                        "check_time": check_time,
                                        "cookie_valid": cookie_valid,
                                        "refresh_status": refresh_status,
                                    }
                                )
                            else:
                                logger.warning(f"[读取] 文件 {filename} 使用旧格式，跳过列表显示")
                    except (json.JSONDecodeError, KeyError, TypeError) as e:
                        logger.error(f"[读取] 解析文件 {filename} 时出错: {e}")
                        # 选择删除或重命名无效的文件
                        # os.rename(file_path, file_path + ".invalid")
        return JSONResponse(content=cookies)


# 随机返回有效cookie
@router.get("/api/cookie/random")
async def get_random_cookie(token: str = Header(None), type: str = Query(None)):
    from core.config import get_config_manager
    config_manager = get_config_manager()
    app_config = config_manager.config
    COOKIE_FOLDER = app_config.cookie.folder

    
    await verify_api_token(token)
    valid_cookies = []
    if os.path.exists(COOKIE_FOLDER):
        for filename in os.listdir(COOKIE_FOLDER):
            if filename.endswith(".json"):
                file_path = os.path.join(COOKIE_FOLDER, filename)
                try:
                    with open(file_path, "r", encoding="utf-8") as file:
                        file_content = file.read().strip()
                        if not file_content:
                            continue
                            
                        cookie_data = json.loads(file_content)
                        DedeUserID = filename.replace(".json", "")
                        
                        if "_cookiemgmt" in cookie_data:
                            is_valid = cookie_data["_cookiemgmt"].get("cookie_valid", False)
                            if is_valid is True:
                                valid_cookies.append(cookie_data)
                        else:
                            logger.warning(f"[随机] 文件 {filename} 使用旧格式，跳过")
                except (json.JSONDecodeError, KeyError) as e:
                    logger.error(f"[随机] 解析文件 {filename} 时出错: {e}")
                    continue
    if not valid_cookies:
        raise HTTPException(status_code=404, detail="无可用的有效 Cookie")
    
    chosen_cookie = random.choice(valid_cookies)
    
    if type == "sim":
        try:
            cookies = chosen_cookie["cookie_info"]["cookies"]
            cookie_dict = {cookie["name"]: cookie["value"] for cookie in cookies}
            required_keys = ["DedeUserID", "DedeUserID__ckMd5", "SESSDATA", "bili_jct", "buvid3", "buvid4"]
            cookie_string = "".join([f"{key}={cookie_dict.get(key, '')};" for key in required_keys])
            return JSONResponse(content={"code": 0, "message": "获取成功", "cookie": cookie_string})
        except KeyError as e:
            logger.error(f"[随机] 生成标准格式Cookie字符串失败: {e}")
            raise HTTPException(status_code=500, detail="生成Cookie字符串失败")

    return JSONResponse(content=chosen_cookie)


# 检查Cookie
@router.get("/api/cookie/check")
async def check_cookie_api(DedeUserID: str = Query(...), token: str = Header(None)):
    await verify_api_token(token)
    result = await check_cookie(DedeUserID)
    if result["code"] == 0:
        return JSONResponse(
            content={"code": 0, "message": "Cookie 有效", "is_valid": True}
        )
    else:
        return JSONResponse(
            content={
                "code": result["code"],
                "message": result["message"],
                "is_valid": False,
            }
        )


# 检查所有Cookie
@router.get("/api/cookie/check_all")
async def check_all_cookies_api(token: str = Header(None)):
    await verify_api_token(token)
    await check_all_cookies()
    return JSONResponse(content={"code": 0, "message": "已检查所有Cookie"})


# 测试Cookie
@router.post("/api/cookie/test")
async def test_cookie_api(
    cookie: str = Body(..., embed=True),
    token: str = Header(None)
):
    await verify_api_token(token)
    if not cookie:
        raise HTTPException(status_code=400, detail="缺少 cookie 参数")

    result = await check_cookie_validity(cookie)
    return JSONResponse(content=result)


# 刷新Cookie
@router.get("/api/cookie/refresh")
async def refresh_cookie_api(DedeUserID: str = Query(...), token: str = Header(None)):
    await verify_api_token(token)
    result = await refresh_cookie(DedeUserID)
    if result["code"] == 0:
        return JSONResponse(
            content={
                "code": 0,
                "message": "刷新成功",
                "expire_time": result["expire_time"],
            }
        )
    else:
        return JSONResponse(
            content={"code": result["code"], "message": result["message"]}
        )


# 刷新所有Cookie
@router.get("/api/cookie/refresh_all")
async def refresh_all_cookies_api(token: str = Header(None)):
    await verify_api_token(token)
    await refresh_expired_cookies()
    return JSONResponse(content={"code": 0, "message": "已刷新所有Cookie"})


# 删除Cookie
@router.delete("/api/cookie/delete")
async def delete_cookie_api(DedeUserID: str = Query(...), token: str = Header(None)):
    await verify_api_token(token)
    file_path = get_cookie_file_path(DedeUserID)
    
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="指定的 Cookie 文件不存在")
        
    try:
        os.remove(file_path)
        logger.info(f"[删除] 用户 {DedeUserID} 的 Cookie 文件已删除")
        await ez_push_gotify(
            "[BiliBiliCookieMgmt] Cookie 删除通知",
            f"用户 {DedeUserID} 的 Cookie 文件已被删除。",
            priority=5
        )
        return JSONResponse(content={"code": 0, "message": "删除成功"})
    except Exception as e:
        logger.error(f"[删除] 删除 Cookie 文件失败: {e}")
        raise HTTPException(status_code=500, detail=f"删除文件失败: {str(e)}")