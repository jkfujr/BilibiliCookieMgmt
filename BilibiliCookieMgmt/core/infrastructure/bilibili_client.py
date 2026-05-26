from __future__ import annotations

"""
Bilibili 客户端
"""

import time, hashlib, urllib.parse, httpx, logging, hmac
from typing import Any, Dict, Optional

from ..utils.wbi import enc_wbi


logger = logging.getLogger(__name__)


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
            logger.error(f"生成二维码网络请求失败: {e}")
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
                logger.warning(f"轮询二维码返回未知错误码: {code}, message: {data.get('message')}")
                return {"code": code, "message": data.get("message", "未知错误")}
        except httpx.HTTPError as e:
            logger.error(f"轮询二维码网络请求失败: {e}")
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
        except httpx.HTTPError as e:
            logger.error(f"检查 Cookie 有效性网络请求失败: {e}")
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
        except Exception as e:
            logger.error(f"获取导航信息失败: {e}")
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
        except httpx.HTTPError as e:
            logger.error(f"获取 buvid 失败: {e}")
            return None

    async def fetch_b_nut(self, header_string: str) -> Optional[Dict[str, Any]]:
        """
        获取 b_nut 信息: GET 调用 www.bilibili.com 主站, 从响应 cookies 解析 b_nut 和 buvid3。
        返回 dict 或 None。
        """
        url = "https://www.bilibili.com"
        headers = {
            "User-Agent": USER_AGENT,
            "Referer": "https://www.bilibili.com/",
            "Cookie": header_string,
        }
        try:
            rsp = await self._client.get(url, headers=headers, timeout=10.0)
            parsed: Dict[str, str] = {}
            b_nut = rsp.cookies.get("b_nut")
            if b_nut:
                parsed["b_nut"] = b_nut
            buvid3 = rsp.cookies.get("buvid3")
            if buvid3:
                parsed["buvid3"] = buvid3
            return parsed if parsed else None
        except httpx.HTTPError as e:
            logger.error(f"获取 b_nut 失败: {e}")
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
            logger.error(f"刷新 Cookie 网络请求失败: {e}")
            return {"code": -1, "message": f"网络错误: {e}"}

    async def get_bili_ticket(self, csrf: str = "") -> Optional[Dict[str, Any]]:
        """
        获取 bili_ticket (用于降低风控)
        API: https://api.bilibili.com/bapis/bilibili.api.ticket.v1.Ticket/GenWebTicket
        成功返回 {"ticket": str, "created_at": int, "ttl": int, "expires": int}; 失败返回 None。
        """
        key = "XgwSnGZ1p"
        ts = str(int(time.time()))
        message = f"ts{ts}"

        # HMAC-SHA256
        hexsign = hmac.new(key.encode(), message.encode(), hashlib.sha256).hexdigest()

        url = "https://api.bilibili.com/bapis/bilibili.api.ticket.v1.Ticket/GenWebTicket"
        params = {
            "key_id": "ec02",
            "hexsign": hexsign,
            "context[ts]": ts,
            "csrf": csrf
        }

        try:
            headers = {"user-agent": USER_AGENT}
            rsp = await self._client.post(url, params=params, headers=headers)
            data = rsp.json()
            if data.get("code") == 0:
                inner = data.get("data", {})
                ticket = inner.get("ticket")
                if not ticket:
                    logger.warning("获取 bili_ticket 返回空 ticket")
                    return None
                created_at = int(inner.get("created_at") or int(time.time()))
                ttl = int(inner.get("ttl") or 0)
                expires = created_at + ttl if ttl > 0 else 0
                return {
                    "ticket": str(ticket),
                    "created_at": created_at,
                    "ttl": ttl,
                    "expires": expires,
                }
            else:
                logger.warning(f"获取 bili_ticket 失败: {data}")
        except Exception as e:
            logger.error(f"获取 bili_ticket 异常: {e}")
        return None

    async def _get_wbi_keys(self, cookie: str = "") -> tuple[str, str]:
        """获取 wbi 签名所需的 img_key 和 sub_key。"""
        url = "https://api.bilibili.com/x/web-interface/nav?"
        headers = {
            "User-Agent": USER_AGENT,
            "Referer": "https://www.bilibili.com/",
        }
        if cookie:
            headers["Cookie"] = cookie
        try:
            rsp = await self._client.get(url, headers=headers, timeout=10.0)
            data = rsp.json()
            if data.get("code") != 0:
                raise ValueError(f"nav 接口返回非零 code: {data.get('code')}")
            img_url = data["data"]["wbi_img"]["img_url"]
            sub_url = data["data"]["wbi_img"]["sub_url"]
            img_key = img_url.rsplit("/", 1)[1].split(".")[0]
            sub_key = sub_url.rsplit("/", 1)[1].split(".")[0]
            return img_key, sub_key
        except Exception as e:
            logger.warning(f"获取 wbi keys 失败: {e}")
            raise

    async def check_risk_control(self, header_string: str, room_id: int = 5440) -> Dict[str, Any]:
        """
        检测账号是否被风控。

        调用弹幕信息接口，通过响应头判断：
        - bili-status-code 为 -352
        - 存在 x-bili-gaia-vvoucher 响应键
        同时满足任一项时认为账号可能被风控。

        Returns:
            {
                "ok": bool,
                "risk_controlled": bool,
                "voucher": str | None,
                "bili_status_code": str | None,
                "status": int,
                "error_message": str | None,
            }
        """
        url = "https://api.live.bilibili.com/xlive/web-room/v1/index/getDanmuInfo"
        headers = {
            "User-Agent": USER_AGENT,
            "Referer": "https://live.bilibili.com/",
            "Cookie": header_string,
        }
        params: Dict[str, Any] = {"room_id": room_id}

        result: Dict[str, Any] = {
            "ok": True,
            "risk_controlled": False,
            "voucher": None,
            "bili_status_code": None,
            "status": 200,
            "error_message": None,
        }

        # 获取 wbi 签名
        try:
            img_key, sub_key = await self._get_wbi_keys(header_string)
            params = enc_wbi(params, img_key, sub_key)
        except Exception as e:
            logger.warning(f"获取 wbi keys 失败: {e}")
            result["ok"] = False
            result["error_message"] = f"WBI 签名获取失败: {e}"
            return result

        try:
            rsp = await self._client.get(url, headers=headers, params=params, timeout=10.0)
            result["status"] = rsp.status_code

            bili_status = rsp.headers.get("bili-status-code")
            voucher = rsp.headers.get("x-bili-gaia-vvoucher")

            result["bili_status_code"] = bili_status
            result["voucher"] = voucher

            if bili_status == "-352" or voucher:
                result["risk_controlled"] = True
                voucher_preview = f"{voucher[:24]}..." if voucher else "(无)"
                logger.warning(f"账号风控检测: bili-status-code={bili_status}, voucher={voucher_preview}")
            else:
                logger.debug(f"账号风控检测: 正常 (bili-status-code={bili_status})")

        except httpx.HTTPError as e:
            logger.error(f"风控检测网络请求失败: {e}")
            result["ok"] = False
            result["status"] = -1
            result["error_message"] = f"网络错误: {e}"
        except Exception as e:
            logger.error(f"风控检测异常: {e}")
            result["ok"] = False
            result["status"] = -1
            result["error_message"] = str(e)

        return result