import json, aiohttp

from core.logs import log, log_print
from core.auth import USER_AGENT

from .manager import read_cookie, get_cookie_file_path

logger = log()


def build_cookie_string(cookies):
    """从cookies列表构建cookie字符串"""
    cookie_dict = {cookie["name"]: cookie["value"] for cookie in cookies}
    return "; ".join([f"{key}={value}" for key, value in cookie_dict.items()])


async def fetch_buvid(cookie_str):
    """使用指定的 cookie 字符串获取 buvid"""
    url = "https://api.bilibili.com/x/frontend/finger/spi"
    headers = {
        "User-Agent": USER_AGENT,
        "Referer": "https://www.bilibili.com/",
        "Cookie": cookie_str,
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=10) as response:
                data = await response.json()
        if data.get("code") == 0:
            logger.debug(f"[buvid] buvid API 响应: {data}")
            return data.get("data", {})
        else:
            logger.error(f"[buvid] 获取 buvid API 请求失败: {data.get('message', '未知错误')}")
            return None
    except Exception as e:
        log_print(f"[buvid] 获取 buvid 时发生网络错误: {e}", "ERROR")
        return None


async def fetch_and_save_buvid(DedeUserID, cookie_str=None):
    """
    获取并保存 buvid 信息到指定用户的 Cookie 文件

    参数:
    - DedeUserID: 用户ID
    - cookie_str: Cookie字符串，如果为None则从文件中读取

    返回:
    - bool: 成功返回True，失败返回False
    """
    try:
        if cookie_str is None:
            cookie_data = read_cookie(DedeUserID)
            if not cookie_data:
                logger.error(f"[buvid] 用户 {DedeUserID} 的 Cookie 文件不存在")
                return False

            cookies = cookie_data["cookie_info"]["cookies"]
            cookie_str = build_cookie_string(cookies)

        buvid_data = await fetch_buvid(cookie_str)
        if not buvid_data or not buvid_data.get("b_3") or not buvid_data.get("b_4"):
            logger.warning(f"[buvid] 用户 {DedeUserID} 的 buvid 获取失败或响应数据不完整")
            return False

        cookie_data = read_cookie(DedeUserID)
        if not cookie_data:
            logger.error(f"[buvid] 用户 {DedeUserID} 的 Cookie 文件不存在，无法保存 buvid")
            return False
        
        cookies = cookie_data["cookie_info"]["cookies"]
        buvid3_exists = False
        buvid4_exists = False
        
        for cookie in cookies:
            if cookie["name"] == "buvid3":
                cookie["value"] = buvid_data.get("b_3")
                buvid3_exists = True
            elif cookie["name"] == "buvid4":
                cookie["value"] = buvid_data.get("b_4")
                buvid4_exists = True
        
        # 不存在则添加buvid
        if not buvid3_exists:
            cookies.append({
                "name": "buvid3",
                "value": buvid_data.get("b_3"),
                "http_only": 0,
                "expires": 0,
                "secure": 0
            })
        
        if not buvid4_exists:
            cookies.append({
                "name": "buvid4",
                "value": buvid_data.get("b_4"),
                "http_only": 0,
                "expires": 0,
                "secure": 0
            })

        file_path = get_cookie_file_path(DedeUserID)
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(cookie_data, f, ensure_ascii=False, indent=4)

        logger.info(f"[buvid] 用户 {DedeUserID} 的 buvid 获取并保存成功")
        return True

    except Exception as e:
        logger.error(f"[buvid] 用户 {DedeUserID} 的 buvid 获取和保存过程中发生错误: {e}")
        return False


async def update_buvid_if_missing(DedeUserID):
    """
    检查指定用户的 Cookie 是否缺少 buvid，如果缺少则获取并保存

    参数:
    - DedeUserID: 用户ID

    返回:
    - bool: 成功或无需更新返回True，失败返回False
    """
    try:
        cookie_data = read_cookie(DedeUserID)
        if not cookie_data:
            logger.error(f"[buvid] 用户 {DedeUserID} 的 Cookie 文件不存在")
            return False

        # 检查 cookies buvid
        cookies = cookie_data["cookie_info"]["cookies"]
        buvid3_exists = any(cookie["name"] == "buvid3" for cookie in cookies)
        buvid4_exists = any(cookie["name"] == "buvid4" for cookie in cookies)
        
        if buvid3_exists and buvid4_exists:
            logger.debug(f"[buvid] 用户 {DedeUserID} 的 buvid 已存在，无需更新")
            return True

        logger.info(f"[buvid] 用户 {DedeUserID} 的 Cookie 缺少 buvid，正在获取...")
        return await fetch_and_save_buvid(DedeUserID)

    except Exception as e:
        logger.error(f"[buvid] 检查用户 {DedeUserID} 的 buvid 时发生错误: {e}")
        return False