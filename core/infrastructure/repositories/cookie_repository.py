from __future__ import annotations

"""
文件系统 Cookie 存储仓库。
存储格式采用两段式: 
{
  "raw": { ... 原始响应 ... },
  "managed": { ... 管理信息 ... }
}
文件名: <DedeUserID>.json
"""

import os, json, aiofiles
from typing import Any, Dict, List, Optional
from datetime import datetime

from ...domain.models import ManagedInfo, CookieStatus, RefreshStatus


# 统一的键名
RAW_KEY = "raw"
MANAGED_KEY = "managed"

class CookieRepository:
    """文件系统实现的 Cookie 仓库。"""

    def __init__(self, base_dir: str):
        self.base_dir = base_dir
        os.makedirs(self.base_dir, exist_ok=True)

    def _file_path(self, dede_user_id: str) -> str:
        return os.path.join(self.base_dir, f"{dede_user_id}.json")

    @staticmethod
    def _extract_cookie_map(raw: Dict[str, Any]) -> Dict[str, str]:
        """从原始响应中提取 cookie 名称到值的映射。"""
        cookies = raw.get("cookie_info", {}).get("cookies", [])
        return {c.get("name"): c.get("value") for c in cookies if isinstance(c, dict)}

    @staticmethod
    def _build_header_string(cookie_map: Dict[str, str]) -> str:
        """构建 HTTP Cookie 头字符串。缺失键使用空字符串填充。"""
        parts = []
        for key in ["SESSDATA", "bili_jct", "buvid3", "buvid4", "DedeUserID", "DedeUserID__ckMd5"]:
            val = cookie_map.get(key, "")
            parts.append(f"{key}={val}")
        return "; ".join(parts)

    @staticmethod
    def _extract_user_id(cookie_map: Dict[str, str]) -> Optional[str]:
        return cookie_map.get("DedeUserID")

    async def save_from_raw(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        """
        根据原始响应保存 Cookie。
        返回写入的完整文档(包含两段式)。
        """
        cookie_map = self._extract_cookie_map(raw)
        dede_user_id = self._extract_user_id(cookie_map)
        if not dede_user_id:
            raise ValueError("原始响应缺少 DedeUserID, 无法确定文件名")

        header_str = self._build_header_string(cookie_map)

        # 若存在旧版管理段, 优先尝试使用 v2/scripts/migrate_v1_to_v2.py 进行 raw 映射；
        # 若脚本不存在或导入失败, 则跳过
        legacy = raw.get("_cookiemgmt", {}) if isinstance(raw.get("_cookiemgmt", {}), dict) else {}
        if legacy:
            try:
                from pathlib import Path
                import importlib.util
                v2_dir = Path(__file__).resolve().parents[4]
                script_path = v2_dir / "scripts" / "migrate_v1_to_v2.py"
                if script_path.exists():
                    spec = importlib.util.spec_from_file_location("migrate_v1_to_v2", str(script_path))
                    if spec and spec.loader:
                        mod = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(mod)  # type: ignore
                        if hasattr(mod, "_build_v2_like_raw"):
                            raw = mod._build_v2_like_raw(raw)  # type: ignore
                            cookie_map = self._extract_cookie_map(raw)
                            dede_user_id = self._extract_user_id(cookie_map)
                            header_str = self._build_header_string(cookie_map)
            except Exception:
                pass

        managed = ManagedInfo(
            DedeUserID=dede_user_id,
            update_time=datetime.now(),
            last_check_time=None,
            last_refresh_time=None,
            refresh_status=RefreshStatus.NOT_NEEDED,
            error_message=None,
            header_string=header_str,
            is_enabled=True,
            status=CookieStatus.UNKNOWN,
            username=None,
        )

        doc = {
            RAW_KEY: raw,
            MANAGED_KEY: managed.to_dict(),
        }

        file_path = self._file_path(dede_user_id)
        async with aiofiles.open(file_path, "w", encoding="utf-8") as f:
            await f.write(json.dumps(doc, ensure_ascii=False, indent=2))

        return doc

    async def get(self, dede_user_id: str) -> Optional[Dict[str, Any]]:
        path = self._file_path(dede_user_id)
        if not os.path.exists(path):
            return None
        try:
            async with aiofiles.open(path, "r", encoding="utf-8") as f:
                content = await f.read()
                return json.loads(content)
        except json.JSONDecodeError:
            return None

    async def list(self) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        if not os.path.isdir(self.base_dir):
            return items
        for name in os.listdir(self.base_dir):
            if not name.endswith(".json"):
                continue
            dede_user_id = name[:-5]
            item = await self.get(dede_user_id)
            if item:
                items.append(item)
        return items

    async def delete(self, dede_user_id: str) -> bool:
        path = self._file_path(dede_user_id)
        if os.path.exists(path):
            os.remove(path)
            return True
        return False

    async def update_check_status(self, dede_user_id: str, valid: bool, error_message: Optional[str] = None, username: Optional[str] = None, header_string: Optional[str] = None) -> Optional[Dict[str, Any]]:
        doc = await self.get(dede_user_id)
        if not doc:
            return None
        managed = doc.get(MANAGED_KEY, {}) if isinstance(doc.get(MANAGED_KEY), dict) else {}
        managed["status"] = CookieStatus.VALID.value if valid else CookieStatus.INVALID.value
        managed["last_check_time"] = datetime.now().isoformat()
        managed["error_message"] = error_message
        if username:
            managed["username"] = username
        if header_string:
            managed["header_string"] = header_string
        doc[MANAGED_KEY] = managed
        path = self._file_path(dede_user_id)
        async with aiofiles.open(path, "w", encoding="utf-8") as f:
            await f.write(json.dumps(doc, ensure_ascii=False, indent=2))
        return doc

    async def update_on_refresh(self, dede_user_id: str, token_info: Dict[str, Any], cookie_info: Dict[str, Any], ts: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """
        刷新成功后更新存储文档: 
        - 更新原始响应中的 token_info 与 cookie_info
        - 依据新的 cookies 重建 header_string
        - 更新管理字段: update_time、last_refresh_time、refresh_status、status、error_message、username
        """
        doc = await self.get(dede_user_id)
        if not doc:
            return None
        raw = doc.get(RAW_KEY, {}) if isinstance(doc.get(RAW_KEY), dict) else {}
        if not isinstance(raw, dict):
            raw = {}
        raw["token_info"] = token_info
        raw["cookie_info"] = cookie_info

        # 重建 header_string
        cookie_map = self._extract_cookie_map(raw)
        header_str = self._build_header_string(cookie_map)

        # 更新管理信息
        managed = doc.get(MANAGED_KEY, {}) if isinstance(doc.get(MANAGED_KEY), dict) else {}
        managed["update_time"] = (datetime.fromtimestamp(ts) if ts else datetime.now()).isoformat()
        managed["last_refresh_time"] = datetime.now().isoformat()
        managed["refresh_status"] = RefreshStatus.SUCCESS.value
        managed["status"] = CookieStatus.VALID.value
        managed["error_message"] = None
        managed["header_string"] = header_str
        managed["username"] = cookie_map.get("DedeUserID")

        doc[RAW_KEY] = raw
        doc[MANAGED_KEY] = managed
        path = self._file_path(dede_user_id)
        async with aiofiles.open(path, "w", encoding="utf-8") as f:
            await f.write(json.dumps(doc, ensure_ascii=False, indent=2))
        return doc

    async def update_refresh_failed(self, dede_user_id: str, error_message: str) -> Optional[Dict[str, Any]]:
        """刷新失败时更新管理信息。"""
        doc = await self.get(dede_user_id)
        if not doc:
            return None
        managed = doc.get(MANAGED_KEY, {}) if isinstance(doc.get(MANAGED_KEY), dict) else {}
        managed["last_refresh_time"] = datetime.now().isoformat()
        managed["refresh_status"] = RefreshStatus.FAILED.value
        managed["error_message"] = error_message
        doc[MANAGED_KEY] = managed
        path = self._file_path(dede_user_id)
        async with aiofiles.open(path, "w", encoding="utf-8") as f:
            await f.write(json.dumps(doc, ensure_ascii=False, indent=2))
        return doc

    async def update_buvid(self, dede_user_id: str, buvid3: Optional[str], buvid4: Optional[str]) -> Optional[Dict[str, Any]]:
        """
        更新原始响应中的 buvid3/buvid4 并重建 header_string。
        buvid3/buvid4 任意为 None 时跳过对应项的更新。
        """
        doc = await self.get(dede_user_id)
        if not doc:
            return None
        raw = doc.get(RAW_KEY, {}) if isinstance(doc.get(RAW_KEY), dict) else {}
        if not isinstance(raw, dict):
            return doc
        cookie_info = raw.get("cookie_info", {})
        cookies = cookie_info.get("cookies", [])

        # 更新或追加 buvid3/4
        def upsert_cookie(name: str, value: str):
            found = False
            for c in cookies:
                if c.get("name") == name:
                    c["value"] = value
                    found = True
                    break
            if not found:
                cookies.append({
                    "name": name,
                    "value": value,
                    "http_only": 0,
                    "expires": 0,
                    "secure": 0,
                })

        if buvid3:
            upsert_cookie("buvid3", buvid3)
        if buvid4:
            upsert_cookie("buvid4", buvid4)

        raw.setdefault("cookie_info", {})["cookies"] = cookies

        # 重建 header_string
        cookie_map = self._extract_cookie_map(raw)
        header_str = self._build_header_string(cookie_map)

        managed = doc.get(MANAGED_KEY, {}) if isinstance(doc.get(MANAGED_KEY), dict) else {}
        managed["header_string"] = header_str
        doc[RAW_KEY] = raw
        doc[MANAGED_KEY] = managed

        path = self._file_path(dede_user_id)
        async with aiofiles.open(path, "w", encoding="utf-8") as f:
            await f.write(json.dumps(doc, ensure_ascii=False, indent=2))
        return doc

    async def update_enabled(self, dede_user_id: str, is_enabled: bool) -> Optional[Dict[str, Any]]:
        """更新启用/禁用状态。"""
        doc = await self.get(dede_user_id)
        if not doc:
            return None
        managed = doc.get(MANAGED_KEY, {}) if isinstance(doc.get(MANAGED_KEY), dict) else {}
        managed["is_enabled"] = bool(is_enabled)
        doc[MANAGED_KEY] = managed
        path = self._file_path(dede_user_id)
        async with aiofiles.open(path, "w", encoding="utf-8") as f:
            await f.write(json.dumps(doc, ensure_ascii=False, indent=2))
        return doc