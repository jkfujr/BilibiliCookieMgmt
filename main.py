import os, time, json, yaml, hashlib, asyncio, aiohttp, uvicorn, urllib.parse, logging

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query, Header
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from logging.handlers import TimedRotatingFileHandler

# 配置文件路径
config_file_path = os.path.join(os.path.dirname(__file__), "config.yaml")
with open(config_file_path, "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)


### 日志模块
def log():
    global logger
    if logging.getLogger().handlers:
        return logging.getLogger()

    script_directory = os.path.dirname(os.path.abspath(__file__))
    log_directory = os.path.join(script_directory, "logs")
    if not os.path.exists(log_directory):
        os.makedirs(log_directory)

    # 日志格式
    log_formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(processName)s - %(message)s"
    )

    default_log_file_name = "ck"
    log_file_path = os.path.join(log_directory, default_log_file_name)
    log_file_handler = TimedRotatingFileHandler(
        log_file_path,
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8",
    )
    log_file_handler.suffix = "%Y-%m-%d.log"
    log_file_handler.setFormatter(log_formatter)
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    logger.addHandler(log_file_handler)

    return logger


logger = log()


### 合并日志与打印信息，用于在控制台也能输出日志信息
def log_print(message, prefix="", level="INFO"):
    """
    用法
    log_print("信息", "等级:     ", "等级")
    """
    if isinstance(level, str):
        level = getattr(logging, level.upper(), logging.INFO)
    # 日志
    logger = logging.getLogger()
    logger.log(level, message)
    # 打印
    print(prefix + message)


# 一些常量
APP_KEY = "4409e2ce8ffd12b8"
APP_SEC = "59b43e04ad6965f34319062b478f83dd"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36 Edg/128.0.0.0"
)

# cookie目录
COOKIE_FOLDER = os.path.join("data", "cookie")

# cookie检查
COOKIE_CHECK_ENABLE = config["COOKIE_CHECK"]["enable"]
COOKIE_CHECK_INTERVAL = config["COOKIE_CHECK"]["check_intlval"]

# cookie刷新
COOKIE_REFRESH_ENABLE = config["COOKIE_REFRESH"]["enable"]
COOKIE_REFRESH_INTERVAL = config["COOKIE_REFRESH"]["refresh_intlval"]


# 为请求参数进行 API 签名
def tvsign(params, appkey=APP_KEY, appsec=APP_SEC):
    params.update({"appkey": appkey})
    params = dict(sorted(params.items()))
    query = urllib.parse.urlencode(params)
    sign = hashlib.md5((query + appsec).encode()).hexdigest()
    params.update({"sign": sign})
    return params


# 获取指定用户的 Cookie 文件路径
def get_cookie_file_path(DedeUserID):
    return os.path.join(COOKIE_FOLDER, f"{DedeUserID}.json")


# 读取指定用户的 Cookie 信息
def read_cookie(DedeUserID):
    file_path = get_cookie_file_path(DedeUserID)
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as file:
            return json.load(file)
    else:
        return None


# 保存登录成功后的 Cookie 信息
def save_cookie_info(login_data):
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


# 刷新指定用户的 Cookie 信息
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
        logger.error("[刷新] 解析失败:", e)
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

        return {
            "code": 0,
            "message": "刷新成功",
            "expire_time": expire_timestamp,
        }
    else:
        logger.error("[刷新] 刷新失败:", rsp_data.get("message", "未知错误"))
        return {
            "code": rsp_data["code"],
            "message": rsp_data.get("message", "刷新失败"),
        }


# 检查指定用户的 Cookie 是否有效
async def check_cookie(DedeUserID):
    cookie_data = read_cookie(DedeUserID)
    if not cookie_data:
        return {"code": -1, "message": "指定用户不存在"}

    cookies = cookie_data["cookie_info"]["cookies"]
    cookie_dict = {cookie["name"]: cookie["value"] for cookie in cookies}
    cookie_str = "; ".join([f"{key}={value}" for key, value in cookie_dict.items()])

    # 检查登录状态
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
        current_ts = int(time.time() * 1000)
        cookie_data["check_time"] = current_ts

        if data.get("code") == 0 and data.get("data", {}).get("isLogin"):
            cookie_data["cookie_valid"] = True
            logger.debug(f"[检查] 用户 {DedeUserID} 的 Cookie 有效")
        else:
            cookie_data["cookie_valid"] = False
            log_print(
                f"[检查] 用户 {DedeUserID} 的 Cookie 无效", "ERROR:     ", "ERROR"
            )

        file_path = get_cookie_file_path(DedeUserID)
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(cookie_data, f, ensure_ascii=False, indent=4)

        if cookie_data["cookie_valid"]:
            return {"code": 0, "message": "Cookie 有效"}
        else:
            return {"code": -2, "message": "Cookie 无效"}
    except Exception as e:
        logger.error(f"[检查] 检查用户 {DedeUserID} 失败: {e}")
        return {"code": -1, "message": "检查失败"}


# 检查所有用户的 Cookie 有效性
async def check_all_cookies():
    if not os.path.exists(COOKIE_FOLDER):
        logger.debug("[检查] Cookie 文件夹不存在，无需检查。")
        return
    tasks = []
    for filename in os.listdir(COOKIE_FOLDER):
        if filename.endswith(".json"):
            DedeUserID = filename.replace(".json", "")
            logger.debug(f"[检查] 正在检查用户 {DedeUserID} 的 Cookie...")
            task = asyncio.create_task(check_cookie(DedeUserID))
            tasks.append(task)
    await asyncio.gather(*tasks)


# 检查并刷新需要更新的 Cookie
async def refresh_expired_cookies():
    if not os.path.exists(COOKIE_FOLDER):
        logger.debug("[刷新] Cookie 文件夹不存在，无需刷新。")
        return
    tasks = []
    for filename in os.listdir(COOKIE_FOLDER):
        if filename.endswith(".json"):
            DedeUserID = filename.replace(".json", "")
            cookie_data = read_cookie(DedeUserID)
            if cookie_data:
                update_time = cookie_data.get("update_time", 0)
                current_time = int(time.time() * 1000)
                elapsed_days = (current_time - update_time) / (1000 * 60 * 60 * 24)
                if elapsed_days >= COOKIE_REFRESH_INTERVAL:
                    logger.info(
                        f"[刷新] 用户 {DedeUserID} 的 Cookie 超过了刷新间隔，正在刷新..."
                    )
                    task = asyncio.create_task(refresh_cookie(DedeUserID))
                    tasks.append(task)
    if tasks:
        await asyncio.gather(*tasks)
    else:
        logger.debug("[刷新] 没有需要刷新的 Cookie。")


# 定时任务：定期检查所有 Cookie
async def periodic_cookie_check():
    try:
        while True:
            logger.debug("[检查] 开始自动检查所有 Cookie 有效性...")
            try:
                await check_all_cookies()
            except Exception as e:
                log_print(f"[检查] 自动检查过程中出现错误: {e}", "ERROR:     ", "ERROR")
            logger.debug(f"[检查] 下一次检查将在 {COOKIE_CHECK_INTERVAL} 秒后进行。")
            await asyncio.sleep(COOKIE_CHECK_INTERVAL)
    except asyncio.CancelledError:
        logger.debug("[检查] 自动 Cookie 检查已取消。")
        raise


# 定时任务：定期刷新需要刷新的 Cookie
async def periodic_cookie_refresh():
    try:
        while True:
            logger.debug("[刷新] 开始自动刷新需要更新的 Cookie...")
            try:
                await refresh_expired_cookies()
            except Exception as e:
                log_print(f"[刷新] 自动刷新过程中出现错误: {e}", "ERROR:     ", "ERROR")
            # 每天检查一次，可以根据需要调整时间间隔
            await asyncio.sleep(24 * 60 * 60)  # 24小时
    except asyncio.CancelledError:
        logger.debug("[刷新] 自动 Cookie 刷新已取消。")
        raise


# 定义应用的生命周期管理
@asynccontextmanager
async def lifespan(app: FastAPI):
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
app = FastAPI(lifespan=lifespan)
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
        print(data)
        if data["code"] == 0:
            login_data = data["data"]
            save_cookie_info(login_data)
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


# 获取所有 Cookie 的简要信息或指定 DedeUserID 的详细信息
@app.get("/api/cookie")
async def get_cookies(DedeUserID: str = Query(None), token: str = Header(None)):
    if DedeUserID:
        await verify_api_token(token)
        cookie_data = read_cookie(DedeUserID)
        if cookie_data:
            expires_in = cookie_data["token_info"]["expires_in"]
            expire_timestamp = cookie_data["update_time"] + int(expires_in) * 1000
            return JSONResponse(
                content={
                    "DedeUserID": DedeUserID,
                    "update_time": cookie_data["update_time"],
                    "expire_time": expire_timestamp,
                    "check_time": cookie_data.get("check_time"),
                    "cookie_valid": cookie_data.get("cookie_valid"),
                }
            )
        else:
            raise HTTPException(status_code=404, detail="未找到指定的 Cookie 信息")
    else:
        cookies = []
        if os.path.exists(COOKIE_FOLDER):
            for filename in os.listdir(COOKIE_FOLDER):
                if filename.endswith(".json"):
                    file_path = os.path.join(COOKIE_FOLDER, filename)
                    with open(file_path, "r", encoding="utf-8") as file:
                        cookie_data = json.load(file)
                        DedeUserID = filename.replace(".json", "")
                        expires_in = cookie_data["token_info"]["expires_in"]
                        expire_timestamp = (
                            cookie_data["update_time"] + int(expires_in) * 1000
                        )
                        cookies.append(
                            {
                                "DedeUserID": DedeUserID,
                                "update_time": cookie_data["update_time"],
                                "expire_time": expire_timestamp,
                                "check_time": cookie_data.get("check_time"),
                                "cookie_valid": cookie_data.get("cookie_valid"),
                            }
                        )
        return JSONResponse(content=cookies)


# 检查指定用户的 Cookie 是否有效
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


# 刷新指定用户的 Cookie 接口
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


# 启动应用
if __name__ == "__main__":
    uvicorn.run(app, host=config["HOST"], port=config["PORT"])
