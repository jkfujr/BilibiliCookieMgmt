from __future__ import annotations

"""
Cookie 业务服务: 封装领域规则, 仅做一件事、写干净的业务逻辑。
"""

import logging
import copy
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from ..infrastructure.repositories.cookie_repository import CookieRepository, MANAGED_KEY, RAW_KEY
from ..infrastructure.bilibili_client import BilibiliClient
from ..infrastructure.notifications import NotificationService, NoopNotificationService

if TYPE_CHECKING:
    from ..config.loader import AppConfig


logger = logging.getLogger(__name__)
SENSITIVE_COOKIE_NAMES = {"b_nut", "bili_ticket"}


@dataclass
class CookieCheckResult:
    status: str
    message: Optional[str]
    document: Optional[Dict[str, Any]]


def _normalize_tags(tags: List[str]) -> List[str]:
    """整理标签输入，去空白、去空值、去重并保持原顺序。"""
    normalized: List[str] = []
    seen = set()
    for tag in tags:
        value = str(tag).strip()
        if not value or value in seen:
            continue
        seen.add(value)
        normalized.append(value)
    return normalized


class CookieService:
    def __init__(self, repository: CookieRepository, config: AppConfig, notification: NotificationService | None = None, bilibili_client: BilibiliClient | None = None):
        self.repo = repository
        self.config = config
        self.notification = notification or NoopNotificationService()
        self.client = bilibili_client

    async def create_from_raw(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        """根据原始响应创建/保存 Cookie 文件。"""
        doc = await self.repo.save_from_raw(raw)
        try:
            info = doc.get(MANAGED_KEY, {}) if isinstance(doc.get(MANAGED_KEY), dict) else {}
            dede_user_id = info.get("DedeUserID")
            logger.info(f"Cookie 创建成功: {dede_user_id}")
            await self.notification.send(
                title="Cookie 创建成功",
                message=f"用户 {dede_user_id} 的 Cookie 已保存。",
                priority=5,
            )
        except Exception as e:
            logger.error(f"Cookie 创建后通知发送失败: {e}", exc_info=True)
        result = self._sanitize_api_doc(doc)
        assert result is not None, "save_from_raw 返回的文档经净化后不应为 None"
        return result

    async def enrich_after_create(self, dede_user_id: str) -> Optional[Dict[str, Any]]:
        """
        扫码创建后置处理:
        - 获取并更新 buvid3/4/b_nut(如可能)
        - 获取 bili_ticket(如启用)
        - 执行首轮有效性检查与用户名写入
        返回净化后的最新文档。
        """
        doc = await self.repo.get(dede_user_id)
        if not doc:
            return None
        info = doc.get(MANAGED_KEY, {}) if isinstance(doc.get(MANAGED_KEY), dict) else {}
        header_string = info.get("header_string", "")

        # 刷新 buvid/b_nut 和 bili_ticket — 互不阻断
        if header_string:
            updated = await self._refresh_buvid_bnut(dede_user_id, header_string)
            if updated:
                doc = updated
            updated = await self._refresh_bili_ticket(dede_user_id)
            if updated:
                doc = updated

        # 首轮检查
        try:
            checked = await self.check_cookie(dede_user_id)
            if checked.document:
                doc = checked.document
        except Exception as e:
            logger.warning(f"扫码后置处理-首轮检查异常: {e}")

        return self._sanitize_api_doc(doc)

    async def get_cookie(self, dede_user_id: str) -> Optional[Dict[str, Any]]:
        return self._sanitize_api_doc(await self.repo.get(dede_user_id))

    async def list_cookies(self) -> List[Dict[str, Any]]:
        docs = await self.repo.list()
        result: List[Dict[str, Any]] = []
        for d in docs:
            clean = self._sanitize_api_doc(d)
            assert clean is not None
            result.append(clean)
        return result

    async def delete_cookie(self, dede_user_id: str) -> bool:
        return await self.repo.delete(dede_user_id)

    async def check_cookie(self, dede_user_id: str) -> CookieCheckResult:
        """
        Cookie 有效性检查(接入 BilibiliClient): 
        - 从存储获取 header_string(若缺失则根据 cookies 构建)
        - 调用客户端 nav 接口判断是否登录
        - 更新仓库中的检查状态, 并在失效时发送通知
        """
        doc = await self.repo.get(dede_user_id)
        if not doc:
            return CookieCheckResult("failed", "Cookie 不存在", None)

        info = doc.get(MANAGED_KEY, {}) if isinstance(doc.get(MANAGED_KEY), dict) else {}
        header_string = info.get("header_string")

        # 检查 header_string 是否符合当前 bili_ticket 配置策略
        should_rebuild = False
        if header_string:
            has_sensitive_cookie = self._has_sensitive_cookie_part(header_string)
            has_ticket = "bili_ticket=" in header_string
            if not self.config.bili.bili_ticket_enabled and has_sensitive_cookie:
                should_rebuild = True
            elif self.config.bili.bili_ticket_enabled and not has_ticket:
                should_rebuild = True

        if not header_string or should_rebuild:
            raw = doc.get(RAW_KEY, {}) if isinstance(doc.get(RAW_KEY), dict) else {}
            cookie_map = CookieRepository._extract_cookie_map(raw)
            header_string = self.repo._build_managed_header_string(cookie_map)

        inspection = (
            await self.client.inspect_cookie(header_string)
            if self.client
            else {
                "status": "failed",
                "message": "Bilibili 客户端未初始化",
                "username": None,
            }
        )
        inspection_status = str(inspection.get("status") or "failed")
        stored_status = inspection_status if inspection_status in {"valid", "invalid"} else None
        error_message = None if inspection_status == "valid" else str(inspection.get("message") or "检查失败")

        result = await self.repo.update_check_result(
            dede_user_id,
            status=stored_status,
            error_message=error_message,
            username=inspection.get("username"),
            header_string=header_string,
        )
        if inspection_status == "failed":
            logger.warning(f"Cookie 检查请求失败: {dede_user_id}, 原因: {error_message}")
        elif inspection_status == "invalid":
            logger.warning(f"Cookie 检查失败: {dede_user_id}, 原因: {error_message}")
        else:
            logger.debug(f"Cookie 检查通过: {dede_user_id}")

        try:
            if inspection_status == "invalid":
                await self.notification.send(
                    title="Cookie 失效",
                    message=f"用户 {dede_user_id} 的 Cookie 已失效, 请尽快处理。",
                    priority=7,
                )
            else:
                pass
        except Exception as e:
            logger.error(f"Cookie 检查通知发送失败: {e}", exc_info=True)
        return CookieCheckResult(inspection_status, error_message, result)

    async def refresh_cookie(self, dede_user_id: str) -> Optional[Dict[str, Any]]:
        """
        Cookie 刷新(接入 BilibiliClient):
        - 使用存储中的 token_info 调用刷新接口
        - 刷新成功后更新 token_info/cookie_info、header_string 与管理字段
        - 获取并更新 buvid3/4/b_nut/bili_ticket(互不阻断)
        - 触发健康检查并发送通知
        """
        doc = await self.repo.get(dede_user_id)
        if not doc or not self.client:
            return doc

        raw = doc.get(RAW_KEY, {}) if isinstance(doc.get(RAW_KEY), dict) else {}
        token_info = raw.get("token_info", {})
        access_token = token_info.get("access_token") or token_info.get("access_key")
        refresh_token = token_info.get("refresh_token")
        if not access_token or not refresh_token:
            return await self.repo.update_refresh_failed(dede_user_id, "缺少 access_token 或 refresh_token")

        try:
            resp = await self.client.refresh_cookie(access_token, refresh_token)
        except Exception as e:
            logger.error(f"Cookie 刷新接口调用异常: {dede_user_id}, 错误: {e}", exc_info=True)
            return await self.repo.update_refresh_failed(dede_user_id, f"刷新接口异常: {e}")

        code = resp.get("code")
        if code != 0:
            message = resp.get("message", "刷新失败")
            logger.warning(f"Cookie 刷新返回错误: {dede_user_id}, code: {code}, message: {message}")
            result = await self.repo.update_refresh_failed(dede_user_id, message)
            try:
                await self.notification.send(
                    title="Cookie 刷新失败",
                    message=f"用户 {dede_user_id} 刷新失败: {message}",
                    priority=6,
                )
            except Exception:
                pass
            return result

        data = resp.get("data", {})
        new_token_info = data.get("token_info", {})
        new_cookie_info = data.get("cookie_info", {})
        ts = resp.get("ts")

        result = await self.repo.update_on_refresh(dede_user_id, new_token_info, new_cookie_info, ts)
        logger.info(f"Cookie 刷新成功: {dede_user_id}")

        # 计算过期时间(用于通知)
        try:
            import time as _t
            expires_in = int(new_token_info.get("expires_in", 0))
            expire_timestamp_ms = (int(ts or _t.time()) + expires_in) * 1000
            expire_time_str = _t.strftime("%Y-%m-%d %H:%M:%S", _t.localtime(expire_timestamp_ms / 1000))
        except Exception:
            expire_time_str = "未知"

        # 获取 buvid/b_nut 和 bili_ticket — 互不阻断
        info = (result or {}).get(MANAGED_KEY, {}) if isinstance((result or {}).get(MANAGED_KEY), dict) else {}
        header_string = info.get("header_string", "")
        if header_string:
            updated = await self._refresh_buvid_bnut(dede_user_id, header_string)
            if updated:
                result = updated
        updated = await self._refresh_bili_ticket(dede_user_id)
        if updated:
            result = updated

        # 刷新后健康检查
        try:
            checked = await self.check_cookie(dede_user_id)
            if checked.document:
                result = checked.document
        except Exception:
            pass

        # 通知刷新成功
        try:
            await self.notification.send(
                title="Cookie 刷新成功",
                message=f"用户 {dede_user_id} 的 Cookie 刷新成功, 有效期至 {expire_time_str}",
                priority=5,
            )
        except Exception:
            pass

        return result

    async def refresh_cookie_if_expiring(self, dede_user_id: str, threshold_seconds: int) -> Dict[str, Any]:
        """按 SESSDATA 有效期处理单个账号。"""
        doc = await self.repo.get(dede_user_id)
        if not doc:
            return {"status": "failed", "message": "Cookie 不存在"}
        raw = doc.get(RAW_KEY, {}) if isinstance(doc.get(RAW_KEY), dict) else {}
        expires = self._get_sessdata_expires(raw)
        if expires is None:
            return {"status": "skipped", "message": "缺少或非法 SESSDATA.expires"}
        if not self._cookie_needs_refresh(expires, threshold_seconds):
            return {"status": "skipped", "message": "尚未临期"}

        result = await self.refresh_cookie(dede_user_id)
        info = result.get(MANAGED_KEY, {}) if result and isinstance(result.get(MANAGED_KEY), dict) else {}
        if info.get("refresh_status") == "success":
            return {"status": "succeeded", "message": "刷新成功"}
        return {"status": "failed", "message": info.get("error_message") or "刷新失败"}

    async def test_cookie(self, header_string: str) -> Dict[str, Any]:
        """
        测试任意 Cookie 字符串是否有效。
        入参: header_string(形如 "SESSDATA=...; bili_jct=...; DedeUserID=...")
        返回: {"code": int, "is_valid": bool, "message": str}
        """
        header_string = str(header_string or "").strip()
        if not header_string:
            return {"code": 400, "is_valid": False, "message": "header_string 不能为空"}

        if not self.client:
            return {"code": 500, "is_valid": False, "message": "Bilibili 客户端未初始化"}

        return await self.client.inspect_cookie(header_string)

    async def set_enabled(self, dede_user_id: str, is_enabled: bool) -> Optional[Dict[str, Any]]:
        """设置启用/禁用状态(仅影响随机 Cookie 选择)。"""
        return self._sanitize_api_doc(await self.repo.update_enabled(dede_user_id, is_enabled))

    async def set_tags(self, dede_user_id: str, tags: List[str]) -> Optional[Dict[str, Any]]:
        """设置账号标签。"""
        return self._sanitize_api_doc(await self.repo.update_tags(dede_user_id, _normalize_tags(tags)))

    async def _refresh_buvid_bnut(self, dede_user_id: str, header_string: str) -> Optional[Dict[str, Any]]:
        """获取并更新 buvid3/buvid4/b_nut。任一失败不影响其他字段。返回最新仓储文档或 None。"""
        if not self.client or not header_string:
            return None
        try:
            buvid_data = await self.client.fetch_buvid(header_string)
        except Exception:
            logger.warning(f"fetch_buvid 异常: {dede_user_id}", exc_info=True)
            buvid_data = None
        try:
            b_nut_data = await self.client.fetch_b_nut(header_string)
        except Exception:
            logger.warning(f"fetch_b_nut 异常: {dede_user_id}", exc_info=True)
            b_nut_data = None

        b3 = (buvid_data or {}).get("b_3")
        b4 = (buvid_data or {}).get("b_4")
        b_nut = (b_nut_data or {}).get("b_nut")

        if b3 or b4 or b_nut:
            try:
                return await self.repo.update_buvid_bnut(dede_user_id, b3, b4, b_nut)
            except Exception as e:
                logger.warning(f"更新 buvid/b_nut 失败: {dede_user_id}, 错误: {e}")
        return None

    async def _refresh_bili_ticket(self, dede_user_id: str) -> Optional[Dict[str, Any]]:
        """获取并更新 bili_ticket。仅在功能启用且有 client 时执行。返回最新仓储文档或 None。"""
        if not self.config.bili.bili_ticket_enabled or not self.client:
            return None
        try:
            doc = await self.repo.get(dede_user_id)
            if not doc:
                return None
            raw = doc.get(RAW_KEY, {}) if isinstance(doc.get(RAW_KEY), dict) else {}
            cookie_map = CookieRepository._extract_cookie_map(raw)
            csrf = cookie_map.get("bili_jct", "")
            ticket = await self.client.get_bili_ticket(csrf)
            if ticket:
                return await self.repo.update_bili_ticket(dede_user_id, ticket)
        except Exception as e:
            logger.warning(f"刷新 bili_ticket 异常: {dede_user_id}, 错误: {e}")
        return None

    @staticmethod
    def _get_sessdata_expires(raw: Dict[str, Any]) -> Optional[int]:
        cookie_info = raw.get("cookie_info")
        if not isinstance(cookie_info, dict):
            return None

        cookies = cookie_info.get("cookies")
        if not isinstance(cookies, list):
            return None

        for cookie in cookies:
            if not isinstance(cookie, dict) or cookie.get("name") != "SESSDATA":
                continue

            expires_value = cookie.get("expires")
            if isinstance(expires_value, bool):
                return None
            if isinstance(expires_value, int):
                expires = expires_value
            elif isinstance(expires_value, str) and expires_value.isdigit():
                expires = int(expires_value)
            else:
                return None
            return expires if expires > 0 else None
        return None

    @staticmethod
    def _cookie_needs_refresh(expires: int, threshold_seconds: int) -> bool:
        return expires - datetime.now().timestamp() < int(threshold_seconds)

    @staticmethod
    def _strip_sensitive_cookie_parts(header_string: str) -> str:
        parts = []
        for part in str(header_string or "").split(";"):
            item = part.strip()
            if not item:
                continue
            name = item.split("=", 1)[0]
            if name not in SENSITIVE_COOKIE_NAMES:
                parts.append(item)
        return "; ".join(parts)

    @classmethod
    def _has_sensitive_cookie_part(cls, header_string: str) -> bool:
        return cls._strip_sensitive_cookie_parts(header_string) != str(header_string or "").strip()

    def _sanitize_api_doc(self, doc: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """当 bili_ticket_enabled 为 False 时，裁剪 API 输出中的 bili_ticket/b_nut。"""
        if not doc or self.config.bili.bili_ticket_enabled:
            return doc
        raw = doc.get(RAW_KEY, {})
        managed = doc.get(MANAGED_KEY, {}) if isinstance(doc.get(MANAGED_KEY), dict) else {}
        header = managed.get("header_string", "")

        cookies = []
        if isinstance(raw, dict):
            cookie_info = raw.get("cookie_info", {})
            if isinstance(cookie_info, dict) and isinstance(cookie_info.get("cookies"), list):
                cookies = cookie_info["cookies"]

        filtered = [
            c for c in cookies
            if not (isinstance(c, dict) and c.get("name") in SENSITIVE_COOKIE_NAMES)
        ]
        header_clean = self._strip_sensitive_cookie_parts(header)
        cookies_changed = len(filtered) != len(cookies)
        header_changed = header_clean != str(header or "").strip()

        if not cookies_changed and not header_changed:
            return doc

        result = copy.deepcopy(doc)
        if cookies_changed:
            result[RAW_KEY]["cookie_info"]["cookies"] = filtered
        if header_changed and isinstance(result.get(MANAGED_KEY), dict):
            result[MANAGED_KEY]["header_string"] = header_clean
        return result

    @staticmethod
    def _ticket_needs_refresh(raw: Dict[str, Any]) -> bool:
        """判断 bili_ticket 是否缺失或将在 12 小时内过期。"""
        cookies = raw.get("cookie_info", {}).get("cookies", [])
        ticket_value = None
        expires_ts = None
        for c in cookies:
            if isinstance(c, dict) and c.get("name") == "bili_ticket":
                ticket_value = c.get("value")
                expires_ts = c.get("expires")
                break
        if not ticket_value:
            return True
        if not expires_ts:
            return True
        try:
            return int(expires_ts) - datetime.now().timestamp() < 43200
        except (TypeError, ValueError):
            return True

    async def refresh_ticket_if_expiring(self, dede_user_id: str) -> Dict[str, Any]:
        """按有效期刷新单个账号的 bili_ticket。"""
        if not self.config.bili.bili_ticket_enabled or not self.client:
            return {"status": "skipped", "message": "bili_ticket 未启用"}
        doc = await self.repo.get(dede_user_id)
        if not doc:
            return {"status": "failed", "message": "Cookie 不存在"}
        raw = doc.get(RAW_KEY, {}) if isinstance(doc.get(RAW_KEY), dict) else {}
        if not self._ticket_needs_refresh(raw):
            return {"status": "skipped", "message": "ticket 尚未临期"}
        updated = await self._refresh_bili_ticket(dede_user_id)
        if updated:
            return {"status": "succeeded", "message": "ticket 刷新成功"}
        return {"status": "failed", "message": "获取 ticket 返回空"}

    async def check_risk_control(self, dede_user_id: str) -> Dict[str, Any]:
        """检查单个有效账号的风控状态。"""
        if not self.config.bili.risk_control_enabled or not self.client:
            return {"status": "skipped", "message": "风控检测未启用"}
        doc = await self.repo.get(dede_user_id)
        if not doc:
            return {"status": "failed", "message": "Cookie 不存在"}
        info = doc.get(MANAGED_KEY, {}) if isinstance(doc.get(MANAGED_KEY), dict) else {}
        header_string = info.get("header_string")
        if not header_string or str(info.get("status")) != "valid":
            return {"status": "skipped", "message": "账号当前不可用"}

        try:
            result = await self.client.check_risk_control(header_string)
            if not result.get("ok"):
                message = result.get("error_message", "检测失败")
                await self.repo.update_risk_control(
                    dede_user_id,
                    checked_ok=False,
                    error_message=message,
                )
                return {"status": "failed", "message": message}
            await self.repo.update_risk_control(
                dede_user_id,
                checked_ok=True,
                risk_controlled=result["risk_controlled"],
                voucher=result.get("voucher"),
            )
            return {
                "status": "succeeded",
                "message": "检测完成",
                "risk_controlled": bool(result["risk_controlled"]),
            }
        except Exception as exc:
            await self.repo.update_risk_control(
                dede_user_id,
                checked_ok=False,
                error_message=str(exc),
            )
            return {"status": "failed", "message": str(exc)}

    async def get_random_cookie(self, fmt: str = "simple") -> Optional[Dict[str, Any]]:
        """
        返回随机且启用且有效的 Cookie。
        - fmt=simple: 返回 {DedeUserID, header_string}
        - 其它: 返回完整文档
        """
        import random
        items = await self.repo.list()
        candidates: List[Dict[str, Any]] = []
        for doc in items:
            info = doc.get(MANAGED_KEY, {}) if isinstance(doc.get(MANAGED_KEY), dict) else {}
            if bool(info.get("is_enabled", True)) and str(info.get("status")) == "valid":
                candidates.append(doc)
        if not candidates:
            return None
        chosen = random.choice(candidates)
        # 先净化确保 header_string 符合当前 ticket 策略
        chosen = self._sanitize_api_doc(chosen)
        assert chosen is not None
        if fmt == "simple":
            info = chosen.get(MANAGED_KEY, {}) if isinstance(chosen.get(MANAGED_KEY), dict) else {}
            return {
                "DedeUserID": info.get("DedeUserID"),
                "header_string": info.get("header_string"),
            }
        return chosen
