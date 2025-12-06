from __future__ import annotations

"""
Bilibili 客户端
"""

import time, hashlib, urllib.parse, httpx
from typing import Any, Dict, Optional


APP_KEY = "4409e2ce8ffd12b8"
APP_SEC = "59b43e04ad6965f34319062b478f83dd"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/136.0.7103.48 Safari/537.36"
)


def tvsign(params: Dict[str, Any], appkey: str = APP_KEY, appsec: str = APP_SEC) -> Dict[str, Any]:
    """TV 签名"""
    signed = dict(params)
    signed.update({"appkey": appkey})
    signed = dict(sorted(signed.items()))
    query = urllib.parse.urlencode(signed)
    sign = hashlib.md5((query + appsec).encode()).hexdigest()
    signed.update({"sign": sign})
    return signed


class BilibiliClient:
    def __init__(self, timeout: float = 10.0):
        self._client = httpx.AsyncClient(timeout=timeout)

    async def aclose(self) -> None:
        await self._client.aclose()

    @staticmethod
    def build_cookie_string(cookies: list[dict]) -> str:
        """从 cookies 列表构建请求头字符串。"""
        cookie_dict = {c.get("name"): c.get("value") for c in cookies if c.get("name")}
        return "; ".join([f"{k}={v}" for k, v in cookie_dict.items()])

    async def generate_qrcode(self) -> Dict[str, Any]:
        """
        生成扫码登录二维码(TV 登录)
        返回结构同官方接口: {"code": int, "data": {"auth_code": str, "qrcode_url": str, ...}}
        """
        url = "https://passport.bilibili.com/x/passport-tv-login/qrcode/auth_code"
        params = tvsign({"local_id": "0", "ts": int(time.time())})
        headers = {"User-Agent": USER_AGENT}
        try:
            rsp = await self._client.post(url, params=params, headers=headers)
            data = rsp.json()
            return {"code": data.get("code"), "data": data.get("data")}
        except httpx.HTTPError as e:
            return {"code": -1, "message": f"网络错误: {e}"}

    async def poll_qrcode_status(self, auth_code: str) -> Dict[str, Any]:
        """
        轮询扫码登录状态(TV 登录)
        返回结构同官方接口: {"code": int, "data": {...}}, 并按常见状态码补充 message。
        - 0: 扫码成功, 返回登录数据
        - 86038: 二维码已失效
        - 86090: 等待扫码
        - 其它: 错误或未知
        """
        url = "https://passport.bilibili.com/x/passport-tv-login/qrcode/poll"
        params = tvsign({"auth_code": auth_code, "local_id": "0", "ts": int(time.time())})
        headers = {"User-Agent": USER_AGENT}
        try:
            rsp = await self._client.post(url, params=params, headers=headers)
            data = rsp.json()
            code = data.get("code")
            if code == 0:
                return {"code": 0, "data": data.get("data")}
            elif code == 86038:
                return {"code": 86038, "message": "二维码已失效"}
            elif code == 86090:
                return {"code": 86090, "message": "等待扫码"}
            elif code == 86039:
                return {"code": 86039, "message": data.get("message", "二维码尚未确认")}
            elif code == 86101:
                # 已扫码待确认
                return {"code": 86101, "message": data.get("message", "已扫码, 等待确认")}
            elif code == -3:
                return {"code": -3, "message": "API校验密匙错误"}
            elif code == -400:
                return {"code": -400, "message": "请求错误"}
            else:
                return {"code": code, "message": data.get("message", "未知错误")}
        except httpx.HTTPError as e:
            return {"code": -1, "message": f"网络错误: {e}"}

    async def check_cookie_valid(self, header_string: str) -> bool:
        """
        检查 Cookie 是否有效: 调用导航接口, 判断是否登录
        - header_string: 形如 "SESSDATA=...; bili_jct=...; DedeUserID=..." 的 Cookie 请求头字符串
        返回布尔值: True 表示有效；False 表示无效或请求失败
        """
        url = "https://api.bilibili.com/x/web-interface/nav"
        headers = {
            "User-Agent": USER_AGENT,
            "Referer": "https://www.bilibili.com/",
            "Cookie": header_string,
        }
        try:
            rsp = await self._client.get(url, headers=headers, timeout=10.0)
            data = rsp.json()
            return bool(data.get("code") == 0 and data.get("data", {}).get("isLogin"))
        except httpx.HTTPError:
            return False

    async def get_nav(self, header_string: str) -> Optional[Dict[str, Any]]:
        """
        获取导航信息(包含 isLogin、uname 等)。
        成功返回 data 字典；失败返回 None。
        """
        url = "https://api.bilibili.com/x/web-interface/nav"
        headers = {
            "User-Agent": USER_AGENT,
            "Referer": "https://www.bilibili.com/",
            "Cookie": header_string,
        }
        try:
            rsp = await self._client.get(url, headers=headers, timeout=10.0)
            data = rsp.json()
            if data.get("code") == 0:
                return data.get("data", {})
            return None
        except Exception:
            return None

    async def fetch_buvid(self, header_string: str) -> Optional[Dict[str, Any]]:
        """
        获取 buvid 信息: 调用 x/frontend/finger/spi 接口, 返回包含 b_3、b_4 字段的字典
        - header_string: Cookie 请求头字符串
        返回: dict 或 None
        """
        url = "https://api.bilibili.com/x/frontend/finger/spi"
        headers = {
            "User-Agent": USER_AGENT,
            "Referer": "https://www.bilibili.com/",
            "Cookie": header_string,
        }
        try:
            rsp = await self._client.get(url, headers=headers, timeout=10.0)
            data = rsp.json()
            if data.get("code") == 0:
                return data.get("data", {})
            return None
        except httpx.HTTPError:
            return None

    async def refresh_cookie(self, access_key: str, refresh_token: str) -> Dict[str, Any]:
        """
        刷新 Token/Cookie: 对应 passport.bilibili.com 的刷新接口
        参数: access_key(access_token)、refresh_token
        返回: 原始响应结构, 形如 {"code": int, "data": { token_info, cookie_info }, "ts": int }
        """
        url = "https://passport.bilibili.com/api/v2/oauth2/refresh_token"
        params = tvsign({
            "access_key": access_key,
            "refresh_token": refresh_token,
            "ts": int(time.time()),
        })
        headers = {
            "content-type": "application/x-www-form-urlencoded",
            "user-agent": USER_AGENT,
        }
        try:
            rsp = await self._client.post(url, params=params, headers=headers)
            data = rsp.json()
            return data
        except httpx.HTTPError as e:
            return {"code": -1, "message": f"网络错误: {e}"}