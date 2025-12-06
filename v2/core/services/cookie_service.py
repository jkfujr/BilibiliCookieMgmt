from __future__ import annotations

"""
Cookie 业务服务: 封装领域规则, 仅做一件事、写干净的业务逻辑。
"""

from typing import Any, Dict, List, Optional

from ..infrastructure.repositories.cookie_repository import CookieRepository, MANAGED_KEY, RAW_KEY
from ..infrastructure.bilibili_client import BilibiliClient
from ..infrastructure.notifications import NotificationService, NoopNotificationService


class CookieService:
    def __init__(self, repository: CookieRepository, notification: NotificationService | None = None, bilibili_client: BilibiliClient | None = None):
        self.repo = repository
        self.notification = notification or NoopNotificationService()
        self.client = bilibili_client

    async def create_from_raw(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        """根据原始响应创建/保存 Cookie 文件。"""
        doc = await self.repo.save_from_raw(raw)
        try:
            info = doc.get(MANAGED_KEY, {}) if isinstance(doc.get(MANAGED_KEY), dict) else {}
            dede_user_id = info.get("DedeUserID") or info.get("dede_user_id")
            await self.notification.send(
                title="Cookie 创建成功",
                message=f"用户 {dede_user_id} 的 Cookie 已保存。",
                priority=5,
            )
        except Exception:
            pass
        return doc

    async def enrich_after_create(self, dede_user_id: str) -> Optional[Dict[str, Any]]:
        """
        扫码创建后置处理: 
        - 获取并更新 buvid3/4(如可能)
        - 执行首轮有效性检查与用户名写入
        返回更新后的文档。
        """
        doc = await self.repo.get(dede_user_id)
        if not doc:
            return None
        info = doc.get(MANAGED_KEY, {}) if isinstance(doc.get(MANAGED_KEY), dict) else {}
        header_string = info.get("header_string", "")

        # 获取 buvid3/4
        if self.client and header_string:
            try:
                buvid_data = await self.client.fetch_buvid(header_string)
                b3 = (buvid_data or {}).get("b_3")
                b4 = (buvid_data or {}).get("b_4")
                if b3 or b4:
                    doc = await self.repo.update_buvid(dede_user_id, b3, b4) or doc
            except Exception:
                pass

        # 首轮检查
        try:
            doc = await self.check_cookie(dede_user_id) or doc
        except Exception:
            pass

        return doc

    async def get_cookie(self, dede_user_id: str) -> Optional[Dict[str, Any]]:
        return await self.repo.get(dede_user_id)

    async def list_cookies(self) -> List[Dict[str, Any]]:
        return await self.repo.list()

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
        if not header_string:
            raw = doc.get(RAW_KEY, {}) if isinstance(doc.get(RAW_KEY), dict) else {}
            cookie_map = CookieRepository._extract_cookie_map(raw)
            header_string = CookieRepository._build_header_string(cookie_map)

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
        except Exception:
            pass
        return result

    async def refresh_cookie(self, dede_user_id: str) -> Optional[Dict[str, Any]]:
        """
        Cookie 刷新(接入 BilibiliClient): 
        - 使用存储中的 token_info 调用刷新接口
        - 刷新成功后更新 token_info/cookie_info、header_string 与管理字段
        - 获取并更新 buvid3/4(如可能)
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
            return await self.repo.update_refresh_failed(dede_user_id, f"刷新接口异常: {e}")

        code = resp.get("code")
        if code != 0:
            message = resp.get("message", "刷新失败")
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

        # 更新文件
        result = await self.repo.update_on_refresh(dede_user_id, new_token_info, new_cookie_info, ts)

        # 计算过期时间(用于通知)
        try:
            import time as _t
            expires_in = int(new_token_info.get("expires_in", 0))
            expire_timestamp_ms = (int(ts or _t.time()) + expires_in) * 1000
            expire_time_str = _t.strftime("%Y-%m-%d %H:%M:%S", _t.localtime(expire_timestamp_ms / 1000))
        except Exception:
            expire_time_str = "未知"

        # 获取 buvid 并更新
        try:
            info = (result or {}).get(MANAGED_KEY, {}) if isinstance((result or {}).get(MANAGED_KEY), dict) else {}
            header_string = info.get("header_string", "")
            buvid_data = await self.client.fetch_buvid(header_string)
            if buvid_data and buvid_data.get("b_3") and buvid_data.get("b_4"):
                result = await self.repo.update_buvid(dede_user_id, buvid_data.get("b_3"), buvid_data.get("b_4"))
        except Exception:
            pass

        # 刷新后健康检查
        try:
            await self.check_cookie(dede_user_id)
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
        - all=True 时, 检查所有“启用”的 Cookie(is_enabled 为 True)。
        返回执行摘要与明细。
        """
        target_ids: List[str] = []
        if all:
            items = await self.repo.list()
            for doc in items:
                info = doc.get(MANAGED_KEY, {}) if isinstance(doc.get(MANAGED_KEY), dict) else {}
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
                if res:
                    details.append({"DedeUserID": uid, "ok": True})
                    succeeded += 1
                else:
                    details.append({"DedeUserID": uid, "ok": False, "message": "未找到或检查失败"})
                    failed += 1
            except Exception as e:
                details.append({"DedeUserID": uid, "ok": False, "message": f"异常: {e}"})
                failed += 1

        return {"ok": True, "total": len(target_ids), "succeeded": succeeded, "failed": failed, "details": details}

    async def refresh_cookies(self, ids: Optional[List[str]] = None, all: bool = False) -> Dict[str, Any]:
        """
        批量刷新 Cookie。
        - ids 提供时, 仅刷新这些用户。
        - all=True 时, 刷新所有“启用”的 Cookie(is_enabled 为 True)。
        返回执行摘要与明细。
        """
        target_ids: List[str] = []
        if all:
            items = await self.repo.list()
            for doc in items:
                info = doc.get(MANAGED_KEY, {}) if isinstance(doc.get(MANAGED_KEY), dict) else {}
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
                if res:
                    details.append({"DedeUserID": uid, "ok": True})
                    succeeded += 1
                else:
                    details.append({"DedeUserID": uid, "ok": False, "message": "未找到或刷新失败"})
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
        return await self.repo.update_enabled(dede_user_id, is_enabled)

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
        if fmt == "simple":
            info = chosen.get(MANAGED_KEY, {}) if isinstance(chosen.get(MANAGED_KEY), dict) else {}
            return {
                "DedeUserID": info.get("DedeUserID"),
                "header_string": info.get("header_string"),
            }
        return chosen