import os, json, time, asyncio, aiohttp

from core.logs import log, log_print
from core.notifications.gotify import ez_push_gotify
from core.auth import USER_AGENT, tvsign

logger = log()

def get_cookie_folder():
    """获取 Cookie 路径"""
    try:
        from core.config.manager import get_config
        app_config = get_config()
        return app_config.cookie.folder
    except RuntimeError:
        return os.path.join("data", "cookie")

COOKIE_FOLDER = get_cookie_folder()


def get_cookie_file_path(DedeUserID):
    """获取 Cookie 路径"""
    return os.path.join(COOKIE_FOLDER, f"{DedeUserID}.json")


def read_cookie(DedeUserID):
    """读取Cookie"""
    file_path = get_cookie_file_path(DedeUserID)
    if os.path.exists(file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as file:
                cookie_data = json.load(file)
                
            if "_cookiemgmt" not in cookie_data:
                logger.info(f"[读取] 检测到用户 {DedeUserID} 使用旧格式，触发自动迁移")
                asyncio.create_task(refresh_cookie(DedeUserID))
                return None
                
            return cookie_data
        except json.JSONDecodeError as e:
            logger.error(f"[读取] 用户 {DedeUserID} 的 Cookie 文件格式无效: {e}")
            return None
    else:
        return None


def save_cookie(login_data):
    """保存Cookie"""
    DedeUserID = ""
    for cookie in login_data["cookie_info"]["cookies"]:
        if cookie["name"] == "DedeUserID":
            DedeUserID = cookie["value"]
            break
    if not DedeUserID:
        logger.warning("未获取到 DedeUserID")
        return

    current_ts = int(time.time() * 1000)
    
    # 获取用户名
    username = None
    for cookie in login_data["cookie_info"]["cookies"]:
        if cookie["name"] == "DedeUserID__ckMd5":
            username = cookie.get("value", "")
            break
    
    save_info = {
        "token_info": login_data["token_info"],
        "cookie_info": login_data["cookie_info"],
        "_cookiemgmt": {
            "update_time": current_ts,
            "username": username,
            "cookie_valid": True,
            "last_check_time": current_ts,
            "last_refresh_time": current_ts,
            "refresh_status": "success",
            "error_message": None
        }
    }

    file_path = get_cookie_file_path(DedeUserID)
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(save_info, f, ensure_ascii=False, indent=4)
    
    # 检查文件是否写入且不为空
    if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
        logger.info(f"[保存] 用户 {DedeUserID} 的 Cookie 保存成功")
    else:
        error_msg = f"[保存] 用户 {DedeUserID} 的 Cookie 文件保存失败或为空"
        log_print(error_msg, "ERROR")
        asyncio.create_task(ez_push_gotify(
            "[BiliBiliCookieMgmt] Cookie 保存异常",
            error_msg,
            priority=5
        ))


async def refresh_cookie(DedeUserID):
    """刷新Cookie"""
    cookie_data = read_cookie(DedeUserID)
    if not cookie_data:
        error_msg = "指定用户不存在"
        return {"code": -1, "message": error_msg}

    access_token = cookie_data["token_info"]["access_token"]
    refresh_token = cookie_data["token_info"]["refresh_token"]

    params = tvsign(
        {
            "access_key": access_token,
            "refresh_token": refresh_token,
            "ts": int(time.time()),
        }
    )

    headers = {
        "content-type": "application/x-www-form-urlencoded",
        "user-agent": USER_AGENT,
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://passport.bilibili.com/api/v2/oauth2/refresh_token",
                params=params,
                headers=headers,
            ) as rsp:
                rsp_data = await rsp.json()
    except Exception as e:
        error_msg = f"请求或解析失败: {e}"
        logger.error(f"[刷新] 解析失败: {e}")
        return {"code": -1, "message": "请求或解析失败"}

    if rsp_data["code"] == 0:
        expires_in = rsp_data["data"]["token_info"]["expires_in"]
        expire_timestamp = (rsp_data["ts"] + int(expires_in)) * 1000
        current_ts = int(time.time() * 1000)
        
        username = None
        for cookie in rsp_data["data"]["cookie_info"]["cookies"]:
            if cookie["name"] == "DedeUserID__ckMd5":
                username = cookie.get("value", "")
                break
        
        save_info = {
            "token_info": rsp_data["data"]["token_info"],
            "cookie_info": rsp_data["data"]["cookie_info"],
            "_cookiemgmt": {
                "update_time": rsp_data["ts"] * 1000,
                "username": username,
                "cookie_valid": True,
                "last_check_time": current_ts,
                "last_refresh_time": current_ts,
                "refresh_status": "success",
                "error_message": None
            }
        }

        file_path = get_cookie_file_path(DedeUserID)
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(save_info, f, ensure_ascii=False, indent=4)

        expire_time_str = time.strftime(
            "%Y-%m-%d %H:%M:%S", time.localtime(expire_timestamp / 1000)
        )

        logger.info(
            f"[刷新] 用户 {DedeUserID} 的 Cookie 刷新成功，有效期至 {expire_time_str}"
        )
        
        await ez_push_gotify(
            "[BiliBiliCookieMgmt] Cookie 刷新通知",
            f"用户 {DedeUserID} 的 Cookie 刷新成功，有效期至 {expire_time_str}",
            priority=5,
        )

        # 刷新后立即获取 buvid
        from .buvid import fetch_and_save_buvid, build_cookie_string
        cookies = save_info["cookie_info"]["cookies"]
        cookie_str = build_cookie_string(cookies)
        await fetch_and_save_buvid(DedeUserID, cookie_str)

        # 健康检查
        from .health import check_cookie
        check_result = await check_cookie(DedeUserID)
        if check_result["code"] == 0:
            logger.info(f"[刷新] 用户 {DedeUserID} 的 Cookie 有效")
        else:
            log_print(f"[检查] 用户 {DedeUserID} 的 Cookie 无效", "WARN")
            await ez_push_gotify(
                "[BiliBiliCookieMgmt] Cookie 失效通知",
                f"用户 {DedeUserID} 的 Cookie 已失效，请尽快处理。",
                priority=5,
            )

        return {
            "code": 0,
            "message": "刷新成功",
            "expire_time": expire_timestamp,
        }
    else:
        error_msg = rsp_data.get('message', '刷新失败')
        logger.error(f"[刷新] 刷新失败: {error_msg}")
        
        return {
            "code": rsp_data["code"],
            "message": error_msg,
        }