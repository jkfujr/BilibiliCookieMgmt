import random
import os, time, json, yaml, hashlib, asyncio, aiohttp, uvicorn, urllib.parse

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
config_file_path = os.path.join(os.path.dirname(__file__), "config.yaml")
with open(config_file_path, "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)


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


# Cookie健康检查
async def check_cookie(DedeUserID):
    cookie_data = read_cookie(DedeUserID)
    if not cookie_data:
        return {"code": -1, "message": "指定用户不存在"}

    cookies = cookie_data["cookie_info"]["cookies"]
    cookie_dict = {cookie["name"]: cookie["value"] for cookie in cookies}
    cookie_str = "; ".join([f"{key}={value}" for key, value in cookie_dict.items()])

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
    for filename in os.listdir(COOKIE_FOLDER):
        if filename.endswith(".json"):
            DedeUserID = filename.replace(".json", "")
            file_path = os.path.join(COOKIE_FOLDER, filename)
            
            # 检查文件是否为空或无效
            try:
                with open(file_path, "r", encoding="utf-8") as file:
                    file_content = file.read().strip()
                    if not file_content:
                        logger.warning(f"[检查] 用户 {DedeUserID} 的 Cookie 文件为空，跳过检查")
                        continue
                    json.loads(file_content)  # 尝试解析JSON
            except (json.JSONDecodeError, IOError) as e:
                logger.error(f"[检查] 用户 {DedeUserID} 的 Cookie 文件无效: {e}")
                continue
                
            logger.debug(f"[检查] 正在检查用户 {DedeUserID} 的 Cookie...")
            task = asyncio.create_task(check_cookie(DedeUserID))
            tasks.append(task)
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
    for filename in os.listdir(COOKIE_FOLDER):
        if filename.endswith(".json"):
            DedeUserID = filename.replace(".json", "")
            file_path = os.path.join(COOKIE_FOLDER, filename)
            
            # 检查文件是否为空或无效
            try:
                with open(file_path, "r", encoding="utf-8") as file:
                    file_content = file.read().strip()
                    if not file_content:
                        logger.warning(f"[刷新] 用户 {DedeUserID} 的 Cookie 文件为空，跳过刷新")
                        continue
                    cookie_data = json.loads(file_content)
            except (json.JSONDecodeError, IOError) as e:
                logger.error(f"[刷新] 用户 {DedeUserID} 的 Cookie 文件无效: {e}")
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
    if tasks:
        await asyncio.gather(*tasks)
    else:
        logger.debug("[刷新] 没有需要刷新的 Cookie。")


# 定时任务-定期检查所有 Cookie
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


# 定时任务-定期刷新需要刷新的 Cookie
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
                            if not file_content:  # 检查文件是否为空
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

# 返回随机有效cookie
@app.get("/api/cookie/random")
async def get_random_cookie(token: str = Header(None)):
    await verify_api_token(token)
    valid_cookies = []
    if os.path.exists(COOKIE_FOLDER):
        for filename in os.listdir(COOKIE_FOLDER):
            if filename.endswith(".json"):
                file_path = os.path.join(COOKIE_FOLDER, filename)
                try:
                    with open(file_path, "r", encoding="utf-8") as file:
                        file_content = file.read().strip()
                        if not file_content:  # 检查文件是否为空
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

# 检查指定Cookie
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



# 启动应用
if __name__ == "__main__":
    uvicorn.run(app, host=config["HOST"], port=config["PORT"])
