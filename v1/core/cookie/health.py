import os, json, time, asyncio, aiohttp

from core.logs import log, log_print
from core.notifications.gotify import ez_push_gotify
from core.auth import USER_AGENT

from .manager import read_cookie, get_cookie_file_path, COOKIE_FOLDER
from .buvid import update_buvid_if_missing, build_cookie_string

logger = log()


async def check_cookie(DedeUserID):
    """Cookie健康检查"""
    
    cookie_data = read_cookie(DedeUserID)
    if not cookie_data:
        error_msg = "指定用户不存在"
        return {"code": -1, "message": error_msg}

    cookies = cookie_data["cookie_info"]["cookies"]
    cookie_str = build_cookie_string(cookies)

    # 检查更新buvid
    await update_buvid_if_missing(DedeUserID)
    cookie_data = read_cookie(DedeUserID)
    if not cookie_data:
        error_msg = "指定用户不存在"
        return {"code": -1, "message": error_msg}

    result = await check_cookie_validity(cookie_str)
    current_ts = int(time.time() * 1000)

    # 更新 cookie_data 中的 _cookiemgmt 字段
    is_valid = result["code"] == 0
    if "_cookiemgmt" not in cookie_data:
        cookie_data["_cookiemgmt"] = {}
    
    cookie_data["_cookiemgmt"]["last_check_time"] = current_ts
    cookie_data["_cookiemgmt"]["cookie_valid"] = is_valid
    if not is_valid:
        cookie_data["_cookiemgmt"]["error_message"] = result.get("message")
    else:
        cookie_data["_cookiemgmt"]["error_message"] = None

    file_path = get_cookie_file_path(DedeUserID)
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(cookie_data, f, ensure_ascii=False, indent=4)

    # 发送通知
    if not is_valid:
        log_print(f"[检查] 用户 {DedeUserID} 的 Cookie 无效", "WARN")
        await ez_push_gotify(
            "[BiliBiliCookieMgmt] Cookie 失效通知",
            f"用户 {DedeUserID} 的 Cookie 已失效, 请尽快处理。",
            priority=3,
        )
    else:
        logger.debug(f"[检查] 用户 {DedeUserID} 的 Cookie 有效")

    return result


async def check_cookie_validity(cookie_str):
    """Cookie健康检查_指定字符串"""
    url = "https://api.bilibili.com/x/web-interface/nav"
    headers = {
        "User-Agent": USER_AGENT,
        "Referer": "https://www.bilibili.com/",
        "Cookie": cookie_str,
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=10) as response:
                data = await response.json()

        if data.get("code") == 0 and data.get("data", {}).get("isLogin"):
            return {"code": 0, "message": "Cookie 有效"}
        else:
            return {"code": -2, "message": "Cookie 无效"}
    except Exception as e:
        log_print(f"[检查] 检查 Cookie 失败: {e}", "ERROR")
        return {"code": -1, "message": "检查失败"}


async def check_all_cookies():
    """Cookie健康检查-所有Cookie"""
    if not os.path.exists(COOKIE_FOLDER):
        logger.debug("[检查] Cookie 文件夹不存在, 无需检查。")
        return
    tasks = []
    empty_files = []
    invalid_files = []
    
    for filename in os.listdir(COOKIE_FOLDER):
        if filename.endswith(".json"):
            DedeUserID = filename.replace(".json", "")
            file_path = os.path.join(COOKIE_FOLDER, filename)
            
            # 检查是否为空
            try:
                with open(file_path, "r", encoding="utf-8") as file:
                    file_content = file.read().strip()
                    if not file_content:
                        logger.warning(f"[检查] 用户 {DedeUserID} 的 Cookie 文件为空, 跳过检查")
                        empty_files.append(DedeUserID)
                        continue
                    json.loads(file_content)
            except (json.JSONDecodeError, IOError) as e:
                logger.error(f"[检查] 用户 {DedeUserID} 的 Cookie 文件无效: {e}")
                invalid_files.append(DedeUserID)
                continue
                
            logger.debug(f"[检查] 正在检查用户 {DedeUserID} 的 Cookie...")
            task = asyncio.create_task(check_cookie(DedeUserID))
            tasks.append(task)
    
    # 发送空文件和无效文件的通知
    if empty_files or invalid_files:
        message = ""
        if empty_files:
            message += f"发现 {len(empty_files)} 个空的 Cookie 文件: {', '.join(empty_files)}\n\n"
        if invalid_files:
            message += f"发现 {len(invalid_files)} 个无效的 Cookie 文件: {', '.join(invalid_files)}"
        
        await ez_push_gotify(
            "[BiliBiliCookieMgmt] Cookie 文件异常",
            message.strip(),
            priority=4
        )
    
    if tasks:
        await asyncio.gather(*tasks)
    else:
        logger.debug("[检查] 没有有效的 Cookie 文件需要检查。")


async def refresh_expired_cookies():
    """Cookie健康检查-每天检查定时刷新"""
    from core.config import get_config_manager
    config_manager = get_config_manager()
    app_config = config_manager.config
    
    if not os.path.exists(COOKIE_FOLDER):
        logger.debug("[刷新] Cookie 文件夹不存在, 无需刷新。")
        return
    tasks = []
    empty_files = []
    invalid_files = []
    
    for filename in os.listdir(COOKIE_FOLDER):
        if filename.endswith(".json"):
            DedeUserID = filename.replace(".json", "")
            file_path = os.path.join(COOKIE_FOLDER, filename)
            
            # 检查空文件
            try:
                with open(file_path, "r", encoding="utf-8") as file:
                    file_content = file.read().strip()
                    if not file_content:
                        logger.warning(f"[刷新] 用户 {DedeUserID} 的 Cookie 文件为空, 跳过刷新")
                        empty_files.append(DedeUserID)
                        continue
                    cookie_data = json.loads(file_content)
            except (json.JSONDecodeError, IOError) as e:
                logger.error(f"[刷新] 用户 {DedeUserID} 的 Cookie 文件无效: {e}")
                invalid_files.append(DedeUserID)
                continue
                
            if cookie_data:
                if "_cookiemgmt" in cookie_data:
                    update_time = cookie_data["_cookiemgmt"].get("update_time", 0)
                    current_time = int(time.time() * 1000)
                    elapsed_days = (current_time - update_time) / (1000 * 60 * 60 * 24)
                    if elapsed_days >= app_config.cookie.refresh_interval:
                        log_print(
                            f"[刷新] 用户 {DedeUserID} 的 Cookie 超过了刷新间隔, 正在刷新...",
                            "INFO",
                        )
                        from .manager import refresh_cookie
                        task = asyncio.create_task(refresh_cookie(DedeUserID))
                        tasks.append(task)
                else:
                    log_print(
                        f"[刷新] 用户 {DedeUserID} 使用旧格式, 立即强制刷新迁移到新格式",
                        "INFO",
                    )
                    from .manager import refresh_cookie
                    task = asyncio.create_task(refresh_cookie(DedeUserID))
                    tasks.append(task)
    
    # 发送空文件通知
    if empty_files or invalid_files:
        message = ""
        if empty_files:
            message += f"刷新时发现 {len(empty_files)} 个空的 Cookie 文件: {', '.join(empty_files)}\n\n"
        if invalid_files:
            message += f"刷新时发现 {len(invalid_files)} 个无效的 Cookie 文件: {', '.join(invalid_files)}"
        
        await ez_push_gotify(
            "[BiliBiliCookieMgmt] Cookie 文件异常",
            message.strip(),
            priority=4
        )
    
    if tasks:
        await asyncio.gather(*tasks)
    else:
        logger.debug("[刷新] 没有需要刷新的 Cookie。")