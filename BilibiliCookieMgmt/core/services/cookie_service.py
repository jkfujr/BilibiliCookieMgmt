from __future__ import annotations

"""
Cookie 业务服务: 封装领域规则, 仅做一件事、写干净的业务逻辑。
"""

import logging
import copy
from datetime import datetime
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from ..infrastructure.repositories.cookie_repository import CookieRepository, MANAGED_KEY, RAW_KEY
from ..infrastructure.bilibili_client import BilibiliClient
from ..infrastructure.notifications import NotificationService, NoopNotificationService

if TYPE_CHECKING:
    from ..config.loader import AppConfig


logger = logging.getLogger(__name__)
SENSITIVE_COOKIE_NAMES = {"b_nut", "bili_ticket"}


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
            if checked:
                doc = checked
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

    async def check_cookie(self, dede_user_id: str) -> Optional[Dict[str, Any]]:
        """
        Cookie 有效性检查(接入 BilibiliClient): 
        - 从存储获取 header_string(若缺失则根据 cookies 构建)
        - 调用客户端 nav 接口判断是否登录
        - 更新仓库中的检查状态, 并在失效时发送通知
        """
        doc = await self.repo.get(dede_user_id)
        if not doc:
            return None

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

        is_valid = True
        error_message: str | None = None
        username_for_update: Optional[str] = None
        if self.client:
            try:
                is_valid = await self.client.check_cookie_valid(header_string)
                if not is_valid:
                    error_message = "Cookie 无效"
                else:
                    try:
                        nav_data = await self.client.get_nav(header_string)
                        if nav_data and nav_data.get("isLogin"):
                            username_for_update = nav_data.get("uname") or nav_data.get("username")
                    except Exception:
                        pass
            except Exception as e:
                is_valid = False
                error_message = f"检查失败: {e}"

        result = await self.repo.update_check_status(
            dede_user_id,
            valid=is_valid,
            error_message=error_message,
            username=username_for_update,
            header_string=header_string,
        )
        if not is_valid:
            logger.warning(f"Cookie 检查失败: {dede_user_id}, 原因: {error_message}")
        else:
            logger.debug(f"Cookie 检查通过: {dede_user_id}")

        # 失效则通知
        try:
            if not is_valid:
                await self.notification.send(
                    title="Cookie 失效",
                    message=f"用户 {dede_user_id} 的 Cookie 已失效, 请尽快处理。",
                    priority=7,
                )
            else:
                pass
        except Exception as e:
            logger.error(f"Cookie 检查通知发送失败: {e}", exc_info=True)
        return result

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
            if checked:
                result = checked
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

    async def check_cookies(self, ids: Optional[List[str]] = None, all: bool = False) -> Dict[str, Any]:
        """
        批量检查 Cookie 有效性。
        - ids 提供时, 仅检查这些用户。
        - all=True 时, 检查所有启用的 Cookie(is_enabled 为 True)。
        返回执行摘要与明细。status 为 valid 计成功, 其余计失败。
        """
        target_ids: List[str] = []
        if all:
            items = await self.repo.list()
            for doc in items:
                info = doc.get(MANAGED_KEY, {}) if isinstance(doc.get(MANAGED_KEY), dict) else {}
                if not info.get("is_enabled", True):
                    continue
                uid = info.get("DedeUserID")
                if uid:
                    target_ids.append(str(uid))
        elif ids:
            target_ids = [str(i) for i in ids if i]

        if not target_ids:
            return {"ok": True, "total": 0, "succeeded": 0, "failed": 0, "details": []}

        details: List[Dict[str, Any]] = []
        succeeded = 0
        failed = 0
        for uid in target_ids:
            try:
                res = await self.check_cookie(uid)
                if not res:
                    details.append({"DedeUserID": uid, "ok": False, "message": "未找到"})
                    failed += 1
                    continue
                info = res.get(MANAGED_KEY, {}) if isinstance(res.get(MANAGED_KEY), dict) else {}
                if info.get("status") == "valid":
                    details.append({"DedeUserID": uid, "ok": True})
                    succeeded += 1
                else:
                    details.append({"DedeUserID": uid, "ok": False, "message": f"状态: {info.get('status')}"})
                    failed += 1
            except Exception as e:
                details.append({"DedeUserID": uid, "ok": False, "message": f"异常: {e}"})
                failed += 1

        return {"ok": True, "total": len(target_ids), "succeeded": succeeded, "failed": failed, "details": details}

    async def refresh_cookies(self, ids: Optional[List[str]] = None, all: bool = False) -> Dict[str, Any]:
        """
        批量刷新 Cookie。
        - ids 提供时, 仅刷新这些用户。
        - all=True 时, 刷新所有启用的 Cookie(is_enabled 为 True)。
        返回执行摘要与明细。refresh_status 为 success 计成功, 其余计失败。
        """
        target_ids: List[str] = []
        if all:
            items = await self.repo.list()
            for doc in items:
                info = doc.get(MANAGED_KEY, {}) if isinstance(doc.get(MANAGED_KEY), dict) else {}
                if not info.get("is_enabled", True):
                    continue
                uid = info.get("DedeUserID")
                if uid:
                    target_ids.append(str(uid))
        elif ids:
            target_ids = [str(i) for i in ids if i]

        if not target_ids:
            return {"ok": True, "total": 0, "succeeded": 0, "failed": 0, "details": []}

        details: List[Dict[str, Any]] = []
        succeeded = 0
        failed = 0
        for uid in target_ids:
            try:
                res = await self.refresh_cookie(uid)
                if not res:
                    details.append({"DedeUserID": uid, "ok": False, "message": "未找到"})
                    failed += 1
                    continue
                info = res.get(MANAGED_KEY, {}) if isinstance(res.get(MANAGED_KEY), dict) else {}
                if info.get("refresh_status") == "success":
                    details.append({"DedeUserID": uid, "ok": True})
                    succeeded += 1
                else:
                    details.append({"DedeUserID": uid, "ok": False, "message": f"刷新状态: {info.get('refresh_status')}"})
                    failed += 1
            except Exception as e:
                details.append({"DedeUserID": uid, "ok": False, "message": f"异常: {e}"})
                failed += 1

        return {"ok": True, "total": len(target_ids), "succeeded": succeeded, "failed": failed, "details": details}

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

        try:
            ok = await self.client.check_cookie_valid(header_string)
            return {"code": 0 if ok else 200, "is_valid": bool(ok), "message": "ok" if ok else "Cookie 无效"}
        except Exception as e:
            return {"code": 502, "is_valid": False, "message": f"检查失败: {e}"}

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

    async def refresh_expiring_tickets(self) -> Dict[str, Any]:
        """
        遍历所有 Cookie，检查 bili_ticket 是否即将过期并刷新。
        仅当 bili_ticket_enabled 为 True 时执行。
        返回执行摘要: {ok, total, refreshed, skipped, failed, details}
        """
        if not self.config.bili.bili_ticket_enabled or not self.client:
            return {"ok": True, "total": 0, "refreshed": 0, "skipped": 0, "failed": 0, "details": []}

        items = await self.repo.list()
        total = 0
        refreshed = 0
        skipped = 0
        failed = 0
        details: List[Dict[str, Any]] = []

        for doc in items:
            info = doc.get(MANAGED_KEY, {}) if isinstance(doc.get(MANAGED_KEY), dict) else {}
            dede_user_id = info.get("DedeUserID")
            if not dede_user_id:
                continue

            total += 1
            raw = doc.get(RAW_KEY, {}) if isinstance(doc.get(RAW_KEY), dict) else {}
            if not self._ticket_needs_refresh(raw):
                skipped += 1
                continue

            try:
                ticket = await self._refresh_bili_ticket(dede_user_id)
                if ticket:
                    refreshed += 1
                    details.append({"DedeUserID": dede_user_id, "ok": True})
                    logger.info(f"bili_ticket 自动刷新成功: {dede_user_id}")
                else:
                    failed += 1
                    details.append({"DedeUserID": dede_user_id, "ok": False, "message": "获取 ticket 返回空"})
            except Exception as e:
                failed += 1
                details.append({"DedeUserID": dede_user_id, "ok": False, "message": str(e)})
                logger.error(f"bili_ticket 自动刷新失败: {dede_user_id}, 错误: {e}")

        if total > 0:
            logger.info(f"bili_ticket 刷新扫描完成: 总计 {total}, 已刷新 {refreshed}, 跳过 {skipped}, 失败 {failed}")

        return {"ok": True, "total": total, "refreshed": refreshed, "skipped": skipped, "failed": failed, "details": details}

    async def check_risk_control_for_all(self) -> Dict[str, Any]:
        """
        遍历所有有效 Cookie 执行风控检测。
        仅当 BILI 配置中 risk_control_enabled 启用时由独立调度任务调用。
        返回执行摘要: {ok, total, checked, failed, details}
        检测失败 (rc["ok"]=False) 不计入 checked, 也不覆盖已有风控状态。
        """
        if not self.config.bili.risk_control_enabled or not self.client:
            return {"ok": True, "total": 0, "checked": 0, "failed": 0, "details": []}

        items = await self.repo.list()
        total = 0
        checked = 0
        failed = 0
        details: List[Dict[str, Any]] = []

        for doc in items:
            info = doc.get(MANAGED_KEY, {}) if isinstance(doc.get(MANAGED_KEY), dict) else {}
            dede_user_id = info.get("DedeUserID")
            header_string = info.get("header_string")
            if not dede_user_id or not header_string:
                continue
            if str(info.get("status")) != "valid":
                continue

            total += 1
            try:
                rc = await self.client.check_risk_control(header_string)
                if not rc.get("ok"):
                    failed += 1
                    details.append({"DedeUserID": dede_user_id, "ok": False, "message": rc.get("error_message", "检测失败")})
                    await self.repo.update_risk_control(
                        dede_user_id,
                        checked_ok=False,
                        error_message=rc.get("error_message", "检测失败"),
                    )
                    logger.warning(f"风控检测失败: {dede_user_id}, 错误: {rc.get('error_message')}")
                    continue

                await self.repo.update_risk_control(
                    dede_user_id,
                    checked_ok=True,
                    risk_controlled=rc["risk_controlled"],
                    voucher=rc.get("voucher"),
                )
                checked += 1
                details.append({"DedeUserID": dede_user_id, "ok": True, "risk_controlled": rc["risk_controlled"]})
                if rc["risk_controlled"]:
                    logger.warning(f"账号风控: {dede_user_id}")
                else:
                    logger.debug(f"风控检测通过: {dede_user_id}")
            except Exception as e:
                failed += 1
                details.append({"DedeUserID": dede_user_id, "ok": False, "message": str(e)})
                await self.repo.update_risk_control(
                    dede_user_id,
                    checked_ok=False,
                    error_message=str(e),
                )
                logger.error(f"风控检测异常: {dede_user_id}, 错误: {e}")

        if total > 0:
            logger.info(f"风控检测扫描完成: 总计 {total}, 已检测 {checked}, 失败 {failed}")

        return {"ok": True, "total": total, "checked": checked, "failed": failed, "details": details}

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
