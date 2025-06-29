import os, time, json, yaml, random, hashlib, asyncio, aiohttp, uvicorn, urllib.parse, sys

from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Query, Header, Body
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from core.gotify import push_gotify
from core.logs import log, log_print

logger = log()

# 一些常量
APP_KEY = "4409e2ce8ffd12b8"
APP_SEC = "59b43e04ad6965f34319062b478f83dd"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36 GLS/100.10.9939.100"

auth_code_cache = {}

# 读取配置
def get_config_path():
    return os.path.join(os.getcwd(), "config.yaml")

try:
    config_file_path = get_config_path()
    if not os.path.exists(config_file_path):
        log_print("配置文件不存在，请确保 config.yaml 文件位于程序运行目录下", "ERROR")
        sys.exit(1)
        
    with open(config_file_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    logger.info(f"成功加载配置文件: {config_file_path}")
except Exception as e:
    log_print(f"加载配置文件失败: {e}", "ERROR")
    sys.exit(1)

# Cookie 目录
COOKIE_FOLDER = os.path.join("data", "cookie")

# Cookie 检查
COOKIE_CHECK_ENABLE = config["COOKIE_CHECK"]["enable"]
COOKIE_CHECK_INTERVAL = config["COOKIE_CHECK"]["check_intlval"]

# Cookie 刷新
COOKIE_REFRESH_ENABLE = config["COOKIE_REFRESH"]["enable"]
COOKIE_REFRESH_INTERVAL = config["COOKIE_REFRESH"]["refresh_intlval"]

# 推送配置
PUSH_CONFIG = config.get("PUSH", {})
## Gotify
GOTIFY_CONFIG = PUSH_CONFIG.get("GOTIFY", {})
GOTIFY_ENABLE = GOTIFY_CONFIG.get("enable", False)
GOTIFY_URL = GOTIFY_CONFIG.get("url", "")
GOTIFY_TOKEN = GOTIFY_CONFIG.get("token", "")


async def ez_push_gotify(title: str, message: str, priority: int = 1):
    """
    发送 Gotify 通知。

    参数:
    - title (str): 消息标题。
    - message (str): 消息内容。
    - priority (int): 消息优先级，默认为1。
    """
    if GOTIFY_ENABLE and GOTIFY_URL and GOTIFY_TOKEN:
        try:
            await push_gotify(
                GOTIFY_URL,
                GOTIFY_TOKEN,
                title,
                message,
                priority=priority,
            )
            logger.info(f"[Gotify] 通知已发送: {title}")
        except Exception as e:
            log_print(f"[Gotify] 推送通知失败: {e}", "ERROR")
    else:
        logger.debug("[Gotify] Gotify 未启用或配置不完整，跳过通知。")

def tvsign(params, appkey=APP_KEY, appsec=APP_SEC):
    params.update({"appkey": appkey})
    params = dict(sorted(params.items()))
    query = urllib.parse.urlencode(params)
    sign = hashlib.md5((query + appsec).encode()).hexdigest()
    params.update({"sign": sign})
    return params


# Cookie文件路径
def get_cookie_file_path(DedeUserID):
    return os.path.join(COOKIE_FOLDER, f"{DedeUserID}.json")


# 读取Cookie
def read_cookie(DedeUserID):
    file_path = get_cookie_file_path(DedeUserID)
    if os.path.exists(file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as file:
                return json.load(file)
        except json.JSONDecodeError as e:
            logger.error(f"[读取] 用户 {DedeUserID} 的 Cookie 文件格式无效: {e}")
            return None
    else:
        return None


# 保存Cookie
def save_cookie(login_data):
    DedeUserID = ""
    for cookie in login_data["cookie_info"]["cookies"]:
        if cookie["name"] == "DedeUserID":
            DedeUserID = cookie["value"]
            break
    if not DedeUserID:
        logger.warning("未获取到 DedeUserID")
        return

    current_ts = int(time.time() * 1000)
    save_info = {
        "update_time": current_ts,
        "token_info": login_data["token_info"],
        "cookie_info": login_data["cookie_info"],
    }

    file_path = get_cookie_file_path(DedeUserID)
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(save_info, f, ensure_ascii=False, indent=4)
    
    # 检查文件是否成功写入且不为空
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


# 刷新Cookie
async def refresh_cookie(DedeUserID):
    cookie_data = read_cookie(DedeUserID)
    if not cookie_data:
        return {"code": -1, "message": "指定用户不存在"}

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
        logger.error(f"[刷新] 解析失败: {e}")
        return {"code": -1, "message": "请求或解析失败"}

    if rsp_data["code"] == 0:
        expires_in = rsp_data["data"]["token_info"]["expires_in"]
        expire_timestamp = (rsp_data["ts"] + int(expires_in)) * 1000
        save_info = {
            "update_time": rsp_data["ts"] * 1000,
            "token_info": rsp_data["data"]["token_info"],
            "cookie_info": rsp_data["data"]["cookie_info"],
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
        cookies = save_info["cookie_info"]["cookies"]
        cookie_str = build_cookie_string(cookies)
        await fetch_and_save_buvid(DedeUserID, cookie_str)

        # 健康检查
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
        logger.error(f"[刷新] 刷新失败: {rsp_data.get('message', '未知错误')}")
        return {
            "code": rsp_data["code"],
            "message": rsp_data.get("message", "刷新失败"),
        }


# 工具函数：从cookies列表构建cookie字符串
def build_cookie_string(cookies):
    """从cookies列表构建cookie字符串"""
    cookie_dict = {cookie["name"]: cookie["value"] for cookie in cookies}
    return "; ".join([f"{key}={value}" for key, value in cookie_dict.items()])


# 获取 buvid
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


# 获取 buvid
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


# 检查 buvid
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

        # 检查 cookies 数组中是否已存在 buvid3 和 buvid4
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


# Cookie健康检查
async def check_cookie(DedeUserID):
    cookie_data = read_cookie(DedeUserID)
    if not cookie_data:
        return {"code": -1, "message": "指定用户不存在"}

    cookies = cookie_data["cookie_info"]["cookies"]
    cookie_str = build_cookie_string(cookies)

    # 检查并更新缺失的 buvid
    await update_buvid_if_missing(DedeUserID)

    # 重新读取 cookie_data，因为 buvid 可能已经被更新
    cookie_data = read_cookie(DedeUserID)
    if not cookie_data:
        return {"code": -1, "message": "指定用户不存在"}

    result = await check_cookie_validity(cookie_str)
    current_ts = int(time.time() * 1000)
    cookie_data["check_time"] = current_ts

    # 更新 cookie_data
    cookie_data["cookie_valid"] = result["code"] == 0
    file_path = get_cookie_file_path(DedeUserID)
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(cookie_data, f, ensure_ascii=False, indent=4)

    # 发送通知
    if not cookie_data["cookie_valid"]:
        log_print(f"[检查] 用户 {DedeUserID} 的 Cookie 无效", "WARN")
        await ez_push_gotify(
            "[BiliBiliCookieMgmt] Cookie 失效通知",
            f"用户 {DedeUserID} 的 Cookie 已失效，请尽快处理。",
            priority=3,
        )
    else:
        logger.debug(f"[检查] 用户 {DedeUserID} 的 Cookie 有效")

    return result


# Cookie健康检查_指定字符串
async def check_cookie_validity(cookie_str):
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


# Cookie健康检查-所有Cookie
async def check_all_cookies():
    if not os.path.exists(COOKIE_FOLDER):
        logger.debug("[检查] Cookie 文件夹不存在，无需检查。")
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
                        logger.warning(f"[检查] 用户 {DedeUserID} 的 Cookie 文件为空，跳过检查")
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


# Cookie健康检查-每天检查定时刷新
async def refresh_expired_cookies():
    if not os.path.exists(COOKIE_FOLDER):
        logger.debug("[刷新] Cookie 文件夹不存在，无需刷新。")
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
                        logger.warning(f"[刷新] 用户 {DedeUserID} 的 Cookie 文件为空，跳过刷新")
                        empty_files.append(DedeUserID)
                        continue
                    cookie_data = json.loads(file_content)
            except (json.JSONDecodeError, IOError) as e:
                logger.error(f"[刷新] 用户 {DedeUserID} 的 Cookie 文件无效: {e}")
                invalid_files.append(DedeUserID)
                continue
                
            if cookie_data:
                update_time = cookie_data.get("update_time", 0)
                current_time = int(time.time() * 1000)
                elapsed_days = (current_time - update_time) / (1000 * 60 * 60 * 24)
                if elapsed_days >= COOKIE_REFRESH_INTERVAL:
                    log_print(
                        f"[刷新] 用户 {DedeUserID} 的 Cookie 超过了刷新间隔，正在刷新...",
                        "INFO",
                    )
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


# 定时-检查所有 Cookie
async def periodic_cookie_check():
    try:
        while True:
            logger.debug("[检查] 开始自动检查所有 Cookie 有效性...")
            try:
                await check_all_cookies()
            except Exception as e:
                log_print(f"[检查] 自动检查过程中出现错误: {e}", "ERROR")
            logger.debug(f"[检查] 下一次检查将在 {COOKIE_CHECK_INTERVAL} 秒后进行。")
            await asyncio.sleep(COOKIE_CHECK_INTERVAL)
    except asyncio.CancelledError:
        logger.debug("[检查] 自动 Cookie 检查已取消。")
        raise


# 定时-刷新需要刷新的 Cookie
async def periodic_cookie_refresh():
    try:
        while True:
            logger.debug("[刷新] 开始自动刷新需要更新的 Cookie...")
            try:
                await refresh_expired_cookies()
            except Exception as e:
                log_print(f"[刷新] 自动刷新过程中出现错误: {e}", "ERROR")
            await asyncio.sleep(24 * 60 * 60)
    except asyncio.CancelledError:
        logger.debug("[刷新] 自动 Cookie 刷新已取消。")
        raise


# 启动函数
@asynccontextmanager
async def run(app: FastAPI):
    tasks = []
    if COOKIE_CHECK_ENABLE:
        logger.debug(
            f"[检查] 自动 Cookie 检查已启用，每隔 {COOKIE_CHECK_INTERVAL} 秒检查一次。"
        )
        check_task = asyncio.create_task(periodic_cookie_check())
        tasks.append(check_task)
    else:
        logger.debug("[检查] 自动 Cookie 检查未启用。")

    if COOKIE_REFRESH_ENABLE:
        logger.debug(
            f"[刷新] 自动 Cookie 刷新已启用，刷新间隔为 {COOKIE_REFRESH_INTERVAL} 天。"
        )
        refresh_task = asyncio.create_task(periodic_cookie_refresh())
        tasks.append(refresh_task)
    else:
        logger.debug("[刷新] 自动 Cookie 刷新未启用。")

    yield

    for task in tasks:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


# FastAPI
app = FastAPI(lifespan=run)
app.mount("/static", StaticFiles(directory="static"), name="static")


# API TOKEN 验证
async def verify_api_token(token: str = Header(None)):
    if config["API_TOKEN"]["enable"]:
        if token != str(config["API_TOKEN"]["token"]):
            raise HTTPException(status_code=401, detail="无效或缺失的 API Token")


@app.get("/")
async def read_root():
    return FileResponse(os.path.join("static", "index.html"))


# 生成二维码
@app.get("/api/passport-login/web/qrcode/generate")
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
@app.get("/api/passport-login/web/qrcode/poll")
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


# 获取Cookie信息
@app.get("/api/cookie")
async def get_cookies(DedeUserID: str = Query(None), token: str = Header(None)):
    if DedeUserID:
        await verify_api_token(token)

        cookie_data = read_cookie(DedeUserID)
        if cookie_data:
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
                            
                            # 检查必要的字段是否存在
                            if "token_info" not in cookie_data or "update_time" not in cookie_data:
                                logger.warning(f"[读取] 文件 {filename} 缺少必要字段，跳过")
                                continue
                                
                            expires_in = cookie_data["token_info"].get("expires_in", 0)
                            expire_timestamp = cookie_data["update_time"] + int(expires_in) * 1000
                            cookies.append(
                                {
                                    "DedeUserID": DedeUserID,
                                    "update_time": cookie_data["update_time"],
                                    "expire_time": expire_timestamp,
                                    "check_time": cookie_data.get("check_time"),
                                    "cookie_valid": cookie_data.get("cookie_valid"),
                                }
                            )
                    except (json.JSONDecodeError, KeyError, TypeError) as e:
                        logger.error(f"[读取] 解析文件 {filename} 时出错: {e}")
                        # 可以选择删除或重命名无效的文件
                        # os.rename(file_path, file_path + ".invalid")
        return JSONResponse(content=cookies)

# 随机返回有效cookie
@app.get("/api/cookie/random")
async def get_random_cookie(token: str = Header(None), type: str = Query(None)):
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
                        if cookie_data.get("cookie_valid") is True:
                            valid_cookies.append(cookie_data)
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
@app.get("/api/cookie/check")
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
@app.get("/api/cookie/check_all")
async def check_all_cookies_api(token: str = Header(None)):
    await verify_api_token(token)
    await check_all_cookies()
    return JSONResponse(content={"code": 0, "message": "已检查所有Cookie"})

# 测试Cookie
@app.post("/api/cookie/test")
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
@app.get("/api/cookie/refresh")
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
@app.get("/api/cookie/refresh_all")
async def refresh_all_cookies_api(token: str = Header(None)):
    await verify_api_token(token)
    await refresh_expired_cookies()
    return JSONResponse(content={"code": 0, "message": "已刷新所有Cookie"})

# 删除Cookie
@app.delete("/api/cookie/delete")
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


# 启动应用
if __name__ == "__main__":
    uvicorn.run(app, host=config["HOST"], port=config["PORT"])
