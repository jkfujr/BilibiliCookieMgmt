from __future__ import annotations

import asyncio
import importlib.util
import json
import logging
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

import httpx
from fastapi.testclient import TestClient


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "BilibiliCookieMgmt"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import core.config.loader as config_loader
from core.infrastructure.repositories.cookie_repository import CookieRepository
from core.infrastructure.bilibili_client import BilibiliClient
from core.services.cookie_service import CookieService
from core.config.loader import AppConfig, load_config


def build_cookie(name: str, value: str) -> dict:
    return {
        "name": name,
        "value": value,
        "http_only": 0,
        "expires": 1893456000,
        "secure": 0,
    }


def build_raw(uid: str, prefix: str = "base") -> dict:
    return {
        "token_info": {
            "access_token": f"access-{uid}",
            "refresh_token": f"refresh-{uid}",
            "expires_in": 3600,
        },
        "cookie_info": {
            "cookies": [
                build_cookie("SESSDATA", f"{prefix}-sess-{uid}"),
                build_cookie("bili_jct", f"{prefix}-csrf-{uid}"),
                build_cookie("buvid3", f"{prefix}-buvid3-{uid}"),
                build_cookie("buvid4", f"{prefix}-buvid4-{uid}"),
                build_cookie("DedeUserID", uid),
                build_cookie("DedeUserID__ckMd5", f"{prefix}-ckmd5-{uid}"),
            ]
        },
    }


def set_cookie_expires(raw: dict, name: str, expires: int | str | None) -> dict:
    for cookie in raw["cookie_info"]["cookies"]:
        if cookie["name"] == name:
            cookie["expires"] = expires
            break
    return raw


def build_legacy_raw(uid: str) -> dict:
    raw = build_raw(uid, prefix="legacy")
    raw["_cookiemgmt"] = {
        "update_time": 1700000000,
        "last_check_time": 1700000100,
        "last_refresh_time": 1700000200,
        "refresh_status": "ok",
        "error_message": None,
        "is_enabled": True,
        "status": "valid",
        "cookie_valid": True,
        "username": f"旧用户{uid}",
    }
    return raw


def write_config(config_path: Path, cookie_dir: Path) -> None:
    data = {
        "HOST": "127.0.0.1",
        "PORT": 18080,
        "API_TOKEN": {
            "enable": True,
            "token": "test-token",
        },
        "STORAGE": {
            "cookie_dir": cookie_dir.as_posix(),
        },
        "GOTIFY": {
            "enable": False,
            "url": "",
            "token": "",
            "priority": 5,
            "title": "BilibiliCookieMgmt",
        },
        "SCHEDULER": {
            "COOKIE_CHECK": {
                "enable": False,
                "interval_seconds": 600,
            },
            "COOKIE_REFRESH": {
                "enable": False,
                "interval_seconds": 86400,
                "scan_interval_seconds": 21600,
            },
            "BILI_TICKET_REFRESH": {
                "interval_seconds": 43200,
            },
            "RISK_CONTROL_CHECK": {
                "interval_seconds": 3600,
            },
        },
        "BILI": {
            "bili_ticket_enabled": False,
            "risk_control_enabled": False,
        },
    }
    config_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_test_app(config_path: Path):
    module_name = f"test_backend_main_{config_path.stem}_{config_path.parent.name}"
    module_path = BACKEND_DIR / "main.py"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("无法加载后端入口模块")

    module = importlib.util.module_from_spec(spec)
    old_argv = sys.argv[:]
    close_log_handlers()
    sys.argv = [module_name, "-c", str(config_path)]
    try:
        spec.loader.exec_module(module)
    finally:
        sys.argv = old_argv
    return module.app


def load_migrate_module():
    module_name = "test_migrate_v1_to_v2"
    module_path = BACKEND_DIR / "scripts" / "migrate_v1_to_v2.py"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("无法加载迁移脚本模块")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def close_log_handlers() -> None:
    logger = logging.getLogger()
    for handler in list(logger.handlers):
        try:
            handler.close()
        finally:
            logger.removeHandler(handler)


class FakeBilibiliClient:
    async def aclose(self) -> None:
        return None

    async def check_cookie_valid(self, header_string: str) -> bool:
        return "invalid" not in header_string

    async def get_nav(self, header_string: str):
        user_id = "unknown"
        for part in header_string.split(";"):
            key, _, value = part.strip().partition("=")
            if key == "DedeUserID":
                user_id = value
                break
        return {"isLogin": True, "uname": f"用户{user_id}"}

    async def fetch_buvid(self, header_string: str):
        return {"b_3": "fake-buvid3", "b_4": "fake-buvid4"}

    async def fetch_b_nut(self, header_string: str):
        return {"b_nut": "fake-bnut-value"}

    async def get_bili_ticket(self, csrf: str = ""):
        return {"ticket": "fake-ticket-value", "created_at": 1700000000, "ttl": 86400, "expires": 1700086400}

    async def check_risk_control(self, header_string: str, room_id: int = 5440):
        return {
            "ok": True,
            "risk_controlled": False,
            "voucher": None,
            "bili_status_code": "0",
            "status": 200,
            "error_message": None,
        }

    async def refresh_cookie(self, access_key: str, refresh_token: str):
        uid = access_key.rsplit("-", 1)[-1]
        return {
            "code": 0,
            "ts": 1700000000,
            "data": {
                "token_info": {
                    "access_token": f"refreshed-access-{uid}",
                    "refresh_token": f"refreshed-refresh-{uid}",
                    "expires_in": 3600,
                },
                "cookie_info": build_raw(uid, prefix="refreshed")["cookie_info"],
            },
        }


class InvalidAfterRefreshClient(FakeBilibiliClient):
    async def refresh_cookie(self, access_key: str, refresh_token: str):
        uid = access_key.rsplit("-", 1)[-1]
        return {
            "code": 0,
            "ts": 1700000000,
            "data": {
                "token_info": {
                    "access_token": f"invalid-access-{uid}",
                    "refresh_token": f"invalid-refresh-{uid}",
                    "expires_in": 3600,
                },
                "cookie_info": build_raw(uid, prefix="invalid")["cookie_info"],
            },
        }


class RaisingRiskClient(FakeBilibiliClient):
    async def check_risk_control(self, header_string: str, room_id: int = 5440):
        raise RuntimeError("risk boom")


class FakeHttpClient:
    def __init__(self, response: httpx.Response):
        self.response = response

    async def get(self, *args, **kwargs):
        return self.response

    async def post(self, *args, **kwargs):
        return self.response

    async def aclose(self) -> None:
        return None


async def fake_wbi_keys(_cookie: str = ""):
    return "a" * 32, "b" * 32


class RepositoryTagTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.cookie_dir = Path(self.temp_dir.name) / "cookies"
        self.repo = CookieRepository(str(self.cookie_dir))

    async def asyncTearDown(self) -> None:
        self.temp_dir.cleanup()

    async def test_default_tags_and_update_clear(self) -> None:
        saved = await self.repo.save_from_raw(build_raw("1001"))
        self.assertEqual(saved["managed"]["tags"], [])
        self.assertTrue(saved["managed"]["join_time"])

        updated = await self.repo.update_tags("1001", ["主力号", "直播"])
        self.assertIsNotNone(updated)
        self.assertEqual(updated["managed"]["tags"], ["主力号", "直播"])
        self.assertEqual(updated["managed"]["join_time"], saved["managed"]["join_time"])

        stored_doc = json.loads((self.cookie_dir / "1001.json").read_text(encoding="utf-8"))
        self.assertEqual(stored_doc["managed"]["tags"], ["主力号", "直播"])

        cleared = await self.repo.update_tags("1001", [])
        self.assertIsNotNone(cleared)
        self.assertEqual(cleared["managed"]["tags"], [])
        self.assertEqual(cleared["managed"]["join_time"], saved["managed"]["join_time"])

    async def test_join_time_is_created_and_preserved_on_resave(self) -> None:
        saved = await self.repo.save_from_raw(build_raw("1101", prefix="first"))
        join_time = saved["managed"]["join_time"]

        resaved = await self.repo.save_from_raw(build_raw("1101", prefix="second"))

        self.assertEqual(resaved["managed"]["join_time"], join_time)
        self.assertIn("second-sess-1101", resaved["managed"]["header_string"])

    async def test_extract_cookie_map_normalizes_to_string_dict(self) -> None:
        cookie_map = self.repo._extract_cookie_map(
            {
                "cookie_info": {
                    "cookies": [
                        {"name": "DedeUserID", "value": 1001},
                        {"name": 2002, "value": None},
                        {"value": "missing-name"},
                        "invalid-cookie",
                    ]
                }
            }
        )

        self.assertEqual(
            cookie_map,
            {
                "DedeUserID": "1001",
                "2002": "",
            },
        )

    async def test_legacy_document_without_tags_is_filled_and_persisted(self) -> None:
        legacy_doc = {
            "raw": build_raw("1002"),
            "managed": {
                "DedeUserID": "1002",
                "update_time": "2026-01-01T00:00:00",
                "last_check_time": None,
                "last_refresh_time": None,
                "refresh_status": "not_needed",
                "error_message": None,
                "header_string": "DedeUserID=1002",
                "is_enabled": True,
                "status": "unknown",
                "username": None,
            },
        }
        legacy_path = self.cookie_dir / "1002.json"
        legacy_path.write_text(json.dumps(legacy_doc, ensure_ascii=False), encoding="utf-8")
        expected_join_time = self.repo._get_file_time(str(legacy_path)).isoformat()

        doc = await self.repo.get("1002")
        self.assertIsNotNone(doc)
        self.assertEqual(doc["managed"]["tags"], [])
        self.assertEqual(doc["managed"]["join_time"], expected_join_time)

        stored_doc = json.loads(legacy_path.read_text(encoding="utf-8"))
        self.assertEqual(stored_doc["managed"]["tags"], [])
        self.assertEqual(stored_doc["managed"]["join_time"], doc["managed"]["join_time"])

    async def test_legacy_document_with_invalid_tags_value_is_rejected(self) -> None:
        legacy_doc = {
            "raw": build_raw("1003"),
            "managed": {
                "DedeUserID": "1003",
                "update_time": "2026-01-01T00:00:00",
                "last_check_time": None,
                "last_refresh_time": None,
                "refresh_status": "not_needed",
                "error_message": None,
                "header_string": "DedeUserID=1003",
                "is_enabled": True,
                "status": "unknown",
                "username": None,
                "tags": None,
            },
        }
        (self.cookie_dir / "1003.json").write_text(json.dumps(legacy_doc, ensure_ascii=False), encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "managed.tags"):
            await self.repo.get("1003")

    async def test_join_time_survives_status_refresh_enabled_and_tag_updates(self) -> None:
        saved = await self.repo.save_from_raw(build_raw("1004"))
        join_time = saved["managed"]["join_time"]

        checked = await self.repo.update_check_status("1004", valid=True, username="用户1004")
        self.assertEqual(checked["managed"]["join_time"], join_time)

        refreshed = await self.repo.update_on_refresh(
            "1004",
            {"access_token": "new-access-1004", "refresh_token": "new-refresh-1004", "expires_in": 3600},
            build_raw("1004", prefix="new")["cookie_info"],
            ts=1700000000,
        )
        self.assertEqual(refreshed["managed"]["join_time"], join_time)

        disabled = await self.repo.update_enabled("1004", False)
        self.assertEqual(disabled["managed"]["join_time"], join_time)

        tagged = await self.repo.update_tags("1004", ["备用"])
        self.assertEqual(tagged["managed"]["join_time"], join_time)

    async def test_header_includes_ticket_when_enabled_and_present(self) -> None:
        repo = CookieRepository(str(self.cookie_dir), bili_ticket_enabled=True)
        raw = build_raw("8001")
        raw["cookie_info"]["cookies"].extend([
            build_cookie("b_nut", "nut-value"),
            build_cookie("bili_ticket", "ticket-value"),
        ])
        saved = await repo.save_from_raw(raw)
        self.assertIn("b_nut=nut-value", saved["managed"]["header_string"])
        self.assertIn("bili_ticket=ticket-value", saved["managed"]["header_string"])

    async def test_header_excludes_ticket_when_disabled(self) -> None:
        repo = CookieRepository(str(self.cookie_dir), bili_ticket_enabled=False)
        raw = build_raw("8002")
        raw["cookie_info"]["cookies"].extend([
            build_cookie("b_nut", "nut-value"),
            build_cookie("bili_ticket", "ticket-value"),
        ])
        saved = await repo.save_from_raw(raw)
        self.assertNotIn("b_nut=", saved["managed"]["header_string"])
        self.assertNotIn("bili_ticket=", saved["managed"]["header_string"])

    async def test_header_no_ticket_placeholder_when_missing(self) -> None:
        repo = CookieRepository(str(self.cookie_dir), bili_ticket_enabled=True)
        raw = build_raw("8003")
        # 不添加 b_nut 和 bili_ticket
        saved = await repo.save_from_raw(raw)
        self.assertNotIn("b_nut=", saved["managed"]["header_string"])
        self.assertNotIn("bili_ticket=", saved["managed"]["header_string"])

    async def test_upsert_cookie_preserves_existing_expires(self) -> None:
        cookies = [{"name": "test", "value": "old", "expires": 99999}]
        CookieRepository._upsert_cookie(cookies, "test", "new")
        self.assertEqual(cookies[0]["value"], "new")
        self.assertEqual(cookies[0]["expires"], 99999)

    async def test_upsert_cookie_overwrites_expires_when_provided(self) -> None:
        cookies = [{"name": "test", "value": "old", "expires": 99999}]
        CookieRepository._upsert_cookie(cookies, "test", "new", expires=12345)
        self.assertEqual(cookies[0]["expires"], 12345)

    async def test_update_on_refresh_replaces_cookie_info_correctly(self) -> None:
        repo = CookieRepository(str(self.cookie_dir), bili_ticket_enabled=True)
        raw = build_raw("8004")
        raw["cookie_info"]["cookies"].extend([
            build_cookie("bili_ticket", "existing-ticket"),
        ])
        saved = await repo.save_from_raw(raw)
        self.assertIn("bili_ticket=existing-ticket", saved["managed"]["header_string"])

        new_cookie_info = build_raw("8004", prefix="refreshed")["cookie_info"]
        # update_on_refresh 会整体替换 cookie_info — ticket 由服务层事后补刷
        refreshed = await repo.update_on_refresh(
            "8004",
            {"access_token": "at", "refresh_token": "rt", "expires_in": 3600},
            new_cookie_info,
            ts=1700000000,
        )
        self.assertEqual(refreshed["managed"]["refresh_status"], "success")
        self.assertEqual(refreshed["raw"]["cookie_info"], new_cookie_info)

    async def test_update_bili_ticket_uses_dict_expires(self) -> None:
        repo = CookieRepository(str(self.cookie_dir), bili_ticket_enabled=True)
        await repo.save_from_raw(build_raw("8005"))
        updated = await repo.update_bili_ticket("8005", {
            "ticket": "new-ticket", "created_at": 1700000000, "ttl": 86400, "expires": 1700086400,
        })
        self.assertIsNotNone(updated)
        cookies = updated["raw"]["cookie_info"]["cookies"]
        ticket_cookie = next(c for c in cookies if c["name"] == "bili_ticket")
        self.assertEqual(ticket_cookie["value"], "new-ticket")
        self.assertEqual(ticket_cookie["expires"], 1700086400)

    async def test_update_risk_control_failure_preserves_old_state(self) -> None:
        repo = CookieRepository(str(self.cookie_dir))
        await repo.save_from_raw(build_raw("8006"))
        # 先写入一个风控状态
        await repo.update_risk_control("8006", checked_ok=True, risk_controlled=True, voucher="old-voucher")
        doc = await repo.get("8006")
        self.assertTrue(doc["managed"]["risk_controlled"])
        self.assertEqual(doc["managed"]["risk_control_voucher"], "old-voucher")

        # 检测失败不覆盖
        await repo.update_risk_control("8006", checked_ok=False, error_message="网络错误")
        doc = await repo.get("8006")
        self.assertTrue(doc["managed"]["risk_controlled"])  # 保持原值
        self.assertEqual(doc["managed"]["risk_control_voucher"], "old-voucher")  # 保持原值
        self.assertEqual(doc["managed"]["risk_control_error_message"], "网络错误")
        self.assertIsNotNone(doc["managed"]["risk_control_checked_at"])


class ServiceTagTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.cookie_dir = Path(self.temp_dir.name) / "cookies"
        self.repo = CookieRepository(str(self.cookie_dir))
        self.service = CookieService(self.repo, AppConfig())
        await self.repo.save_from_raw(build_raw("2001"))

    async def asyncTearDown(self) -> None:
        self.temp_dir.cleanup()

    async def test_service_normalizes_tags(self) -> None:
        updated = await self.service.set_tags("2001", [" 主力号 ", "直播", "主力号", "", "  ", "直播 "])
        self.assertIsNotNone(updated)
        self.assertEqual(updated["managed"]["tags"], ["主力号", "直播"])


class ApiTagTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.cookie_dir = self.root / "cookies"
        self.config_path = self.root / "config.json"
        write_config(self.config_path, self.cookie_dir)

        self.app = load_test_app(self.config_path)
        self.app.state.cookie_service.client = FakeBilibiliClient()
        self.repo = self.app.state.cookie_service.repo
        asyncio.run(self._seed_data())

        self.client = TestClient(self.app)
        self.auth_headers = {"Authorization": "Bearer test-token"}

    def tearDown(self) -> None:
        self.client.close()
        close_log_handlers()
        self.temp_dir.cleanup()

    async def _seed_data(self) -> None:
        await self.repo.save_from_raw(build_raw("3001"))
        await self.repo.save_from_raw(build_raw("3002"))
        await self.repo.update_check_status("3001", valid=True, username="用户3001")
        await self.repo.update_check_status("3002", valid=False, username="用户3002")

    def test_patch_tags_updates_and_list_returns_tags(self) -> None:
        response = self.client.patch(
            "/api/v1/cookies/3001/tags",
            headers=self.auth_headers,
            json={"tags": [" 主力号 ", "直播", "主力号", "", "  "]},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["managed"]["tags"], ["主力号", "直播"])

        list_response = self.client.get("/api/v1/cookies/", headers=self.auth_headers)
        self.assertEqual(list_response.status_code, 200)
        items = {item["managed"]["DedeUserID"]: item for item in list_response.json()}
        self.assertEqual(items["3001"]["managed"]["tags"], ["主力号", "直播"])
        self.assertTrue(items["3001"]["managed"]["join_time"])
        self.assertEqual(items["3002"]["managed"]["tags"], [])
        self.assertTrue(items["3002"]["managed"]["join_time"])

    def test_patch_tags_supports_clear_and_missing_account(self) -> None:
        set_response = self.client.patch(
            "/api/v1/cookies/3001/tags",
            headers=self.auth_headers,
            json={"tags": ["备用"]},
        )
        self.assertEqual(set_response.status_code, 200)
        self.assertEqual(set_response.json()["managed"]["tags"], ["备用"])

        clear_response = self.client.patch(
            "/api/v1/cookies/3001/tags",
            headers=self.auth_headers,
            json={"tags": []},
        )
        self.assertEqual(clear_response.status_code, 200)
        self.assertEqual(clear_response.json()["managed"]["tags"], [])

        missing_response = self.client.patch(
            "/api/v1/cookies/9999/tags",
            headers=self.auth_headers,
            json={"tags": ["不存在"]},
        )
        self.assertEqual(missing_response.status_code, 404)

    def test_tag_updates_do_not_break_existing_cookie_flows(self) -> None:
        tag_response = self.client.patch(
            "/api/v1/cookies/3001/tags",
            headers=self.auth_headers,
            json={"tags": ["主力号", "直播"]},
        )
        self.assertEqual(tag_response.status_code, 200)

        random_response = self.client.get("/api/v1/cookies/random?format=simple", headers=self.auth_headers)
        self.assertEqual(random_response.status_code, 200)
        self.assertEqual(random_response.json()["DedeUserID"], "3001")

        check_response = self.client.post(
            "/api/v1/cookies/check?all=false",
            headers=self.auth_headers,
            json={"ids": ["3001"]},
        )
        self.assertEqual(check_response.status_code, 200)
        self.assertTrue(check_response.json()["details"][0]["ok"])

        refresh_response = self.client.post(
            "/api/v1/cookies/refresh?all=false",
            headers=self.auth_headers,
            json={"ids": ["3001"]},
        )
        self.assertEqual(refresh_response.status_code, 200)
        self.assertTrue(refresh_response.json()["details"][0]["ok"])

        cookie_response = self.client.get("/api/v1/cookies/3001", headers=self.auth_headers)
        self.assertEqual(cookie_response.status_code, 200)
        cookie_doc = cookie_response.json()
        self.assertEqual(cookie_doc["managed"]["tags"], ["主力号", "直播"])
        self.assertEqual(cookie_doc["managed"]["status"], "valid")
        self.assertTrue(cookie_doc["managed"]["join_time"])

    def test_legacy_document_without_tags_is_filled_by_api(self) -> None:
        legacy_doc = {
            "raw": build_raw("3999"),
            "managed": {
                "DedeUserID": "3999",
                "update_time": "2026-01-01T00:00:00",
                "last_check_time": None,
                "last_refresh_time": None,
                "refresh_status": "not_needed",
                "error_message": None,
                "header_string": "SESSDATA=test; DedeUserID=3999",
                "is_enabled": True,
                "status": "unknown",
                "username": "旧用户3999",
            },
        }
        (self.cookie_dir / "3999.json").write_text(json.dumps(legacy_doc, ensure_ascii=False), encoding="utf-8")

        response = self.client.get("/api/v1/cookies/3999", headers=self.auth_headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["managed"]["tags"], [])
        self.assertTrue(response.json()["managed"]["join_time"])

        stored_doc = json.loads((self.cookie_dir / "3999.json").read_text(encoding="utf-8"))
        self.assertEqual(stored_doc["managed"]["tags"], [])
        self.assertEqual(stored_doc["managed"]["join_time"], response.json()["managed"]["join_time"])

    def test_get_settings_masks_sensitive_values(self) -> None:
        response = self.client.get("/api/v1/settings/", headers=self.auth_headers)

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["API_TOKEN"]["token"], {"configured": True, "masked": "****"})
        self.assertEqual(body["GOTIFY"]["token"], {"configured": False, "masked": ""})
        self.assertEqual(body["SCHEDULER"]["COOKIE_REFRESH"]["scan_interval_seconds"], 21600)
        self.assertNotIn("enable", body["SCHEDULER"]["BILI_TICKET_REFRESH"])

    def test_update_settings_preserves_overwrites_and_clears_tokens(self) -> None:
        settings = self.client.get("/api/v1/settings/", headers=self.auth_headers).json()

        settings["API_TOKEN"]["token"] = {}
        settings["GOTIFY"]["token"] = {"value": "gotify-token"}
        response = self.client.put("/api/v1/settings/", headers=self.auth_headers, json=settings)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["restart_required"])
        self.assertEqual(self.app.state.config.api_token.token, "test-token")
        self.assertEqual(self.app.state.config.gotify.token, "gotify-token")

        settings = response.json()["settings"]
        settings["API_TOKEN"]["token"] = {"value": "new-token"}
        settings["GOTIFY"]["token"] = {"value": ""}
        response = self.client.put("/api/v1/settings/", headers=self.auth_headers, json=settings)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.app.state.config.api_token.token, "new-token")
        self.assertEqual(self.app.state.config.gotify.token, "")

        saved = json.loads(self.config_path.read_text(encoding="utf-8"))
        self.assertEqual(saved["API_TOKEN"]["token"], "new-token")
        self.assertEqual(saved["GOTIFY"]["token"], "")

    def test_update_settings_does_not_save_legacy_ticket_refresh_enable(self) -> None:
        settings = self.client.get("/api/v1/settings/", headers=self.auth_headers).json()
        settings["API_TOKEN"]["token"] = {}
        settings["GOTIFY"]["token"] = {}
        settings["SCHEDULER"]["BILI_TICKET_REFRESH"]["enable"] = False
        settings["BILI"]["bili_ticket_enabled"] = True

        response = self.client.put("/api/v1/settings/", headers=self.auth_headers, json=settings)

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("enable", response.json()["settings"]["SCHEDULER"]["BILI_TICKET_REFRESH"])
        saved = json.loads(self.config_path.read_text(encoding="utf-8"))
        self.assertNotIn("enable", saved["SCHEDULER"]["BILI_TICKET_REFRESH"])
        self.assertTrue(self.app.state.config.bili.bili_ticket_enabled)

    def test_update_settings_reports_restart_required_for_base_config(self) -> None:
        settings = self.client.get("/api/v1/settings/", headers=self.auth_headers).json()
        settings["API_TOKEN"]["token"] = {}
        settings["GOTIFY"]["token"] = {}
        settings["PORT"] = 18081

        response = self.client.put("/api/v1/settings/", headers=self.auth_headers, json=settings)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["restart_required"])
        self.assertEqual(self.app.state.config.port, 18081)

    def test_update_settings_restarts_scheduler_when_scheduler_changes(self) -> None:
        with self.client:
            old_scheduler = self.app.state.scheduler
            settings = self.client.get("/api/v1/settings/", headers=self.auth_headers).json()
            settings["API_TOKEN"]["token"] = {}
            settings["GOTIFY"]["token"] = {}
            settings["SCHEDULER"]["COOKIE_CHECK"]["enable"] = True
            settings["SCHEDULER"]["COOKIE_CHECK"]["interval_seconds"] = 60

            response = self.client.put("/api/v1/settings/", headers=self.auth_headers, json=settings)

            self.assertEqual(response.status_code, 200)
            self.assertIsNot(self.app.state.scheduler, old_scheduler)
            self.assertTrue(self.app.state.config.scheduler.cookie_check.enable)


class TicketAndRiskServiceTests(unittest.IsolatedAsyncioTestCase):
    """bili_ticket 和风控相关的服务层回归测试。"""

    async def asyncSetUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.cookie_dir = Path(self.temp_dir.name) / "cookies"
        self.repo = CookieRepository(str(self.cookie_dir))
        config = AppConfig()
        self.client = FakeBilibiliClient()
        self.service = CookieService(self.repo, config, bilibili_client=self.client)
        await self.repo.save_from_raw(build_raw("9001"))
        await self.repo.update_check_status("9001", valid=True, username="用户9001")

    async def asyncTearDown(self) -> None:
        self.temp_dir.cleanup()

    async def test_get_random_cookie_simple_strips_ticket_when_disabled(self) -> None:
        doc = await self.repo.get("9001")
        raw = doc["raw"]
        raw["cookie_info"]["cookies"].extend([
            build_cookie("b_nut", "secret-nut"),
            build_cookie("bili_ticket", "secret-ticket"),
        ])
        # 直接覆写文件以注入敏感字段
        import json, aiofiles
        async with aiofiles.open(self.cookie_dir / "9001.json", "w", encoding="utf-8") as f:
            await f.write(json.dumps(doc, ensure_ascii=False, indent=2))

        result = await self.service.get_random_cookie(fmt="simple")
        self.assertIsNotNone(result)
        self.assertNotIn("b_nut=", result["header_string"])
        self.assertNotIn("bili_ticket=", result["header_string"])

    async def test_api_sanitizer_strips_legacy_managed_header_only_secrets(self) -> None:
        doc = await self.repo.get("9001")
        doc["managed"]["header_string"] = (
            f"{doc['managed']['header_string']}; b_nut=legacy-nut; bili_ticket=legacy-ticket"
        )
        (self.cookie_dir / "9001.json").write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")

        random_simple = await self.service.get_random_cookie(fmt="simple")
        self.assertIsNotNone(random_simple)
        self.assertNotIn("b_nut=", random_simple["header_string"])
        self.assertNotIn("bili_ticket=", random_simple["header_string"])

        got = await self.service.get_cookie("9001")
        self.assertIsNotNone(got)
        self.assertNotIn("b_nut=", got["managed"]["header_string"])
        self.assertNotIn("bili_ticket=", got["managed"]["header_string"])

        listed = await self.service.list_cookies()
        self.assertEqual(len(listed), 1)
        self.assertNotIn("b_nut=", listed[0]["managed"]["header_string"])
        self.assertNotIn("bili_ticket=", listed[0]["managed"]["header_string"])

    async def test_check_cookies_counts_invalid_as_failed(self) -> None:
        async def fake_invalid(_hs: str) -> bool:
            return False
        self.client.check_cookie_valid = fake_invalid
        summary = await self.service.check_cookies(ids=["9001"])
        self.assertEqual(summary["succeeded"], 0)
        self.assertEqual(summary["failed"], 1)

    async def test_refresh_cookies_counts_failed_status(self) -> None:
        async def fake_failed_refresh(_ak: str, _rt: str):
            return {"code": -1, "message": "mock 刷新失败"}
        self.client.refresh_cookie = fake_failed_refresh
        summary = await self.service.refresh_cookies(ids=["9001"])
        self.assertEqual(summary["succeeded"], 0)
        self.assertEqual(summary["failed"], 1)

    async def test_refresh_cookie_returns_final_checked_document(self) -> None:
        self.service.client = InvalidAfterRefreshClient()

        result = await self.service.refresh_cookie("9001")
        stored = await self.repo.get("9001")

        self.assertIsNotNone(result)
        self.assertEqual(result["managed"]["status"], "invalid")
        self.assertEqual(stored["managed"]["status"], "invalid")
        self.assertEqual(result["managed"]["last_check_time"], stored["managed"]["last_check_time"])

    async def test_refresh_expiring_cookies_skips_when_sessdata_not_expiring(self) -> None:
        doc = await self.repo.get("9001")
        raw = set_cookie_expires(doc["raw"], "SESSDATA", int(time.time()) + 90 * 86400)
        doc["raw"] = raw
        doc["managed"]["last_refresh_time"] = None
        (self.cookie_dir / "9001.json").write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")

        summary = await self.service.refresh_expiring_cookies(30 * 86400)
        stored = await self.repo.get("9001")

        self.assertEqual(summary["total"], 1)
        self.assertEqual(summary["refreshed"], 0)
        self.assertEqual(summary["skipped"], 1)
        self.assertEqual(stored["managed"]["last_refresh_time"], None)
        self.assertEqual(stored["managed"]["refresh_status"], "not_needed")

    async def test_refresh_expiring_cookies_refreshes_when_sessdata_expiring(self) -> None:
        doc = await self.repo.get("9001")
        raw = set_cookie_expires(doc["raw"], "SESSDATA", int(time.time()) + 3600)
        doc["raw"] = raw
        (self.cookie_dir / "9001.json").write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")

        summary = await self.service.refresh_expiring_cookies(30 * 86400)
        stored = await self.repo.get("9001")

        self.assertEqual(summary["total"], 1)
        self.assertEqual(summary["refreshed"], 1)
        self.assertEqual(summary["skipped"], 0)
        self.assertEqual(stored["managed"]["refresh_status"], "success")
        self.assertIn("refreshed-sess-9001", stored["managed"]["header_string"])

    async def test_refresh_expiring_cookies_skips_invalid_sessdata_expires(self) -> None:
        doc = await self.repo.get("9001")
        raw = set_cookie_expires(doc["raw"], "SESSDATA", "bad-expires")
        doc["raw"] = raw
        (self.cookie_dir / "9001.json").write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")

        summary = await self.service.refresh_expiring_cookies(30 * 86400)
        stored = await self.repo.get("9001")

        self.assertEqual(summary["total"], 1)
        self.assertEqual(summary["refreshed"], 0)
        self.assertEqual(summary["skipped"], 1)
        self.assertIn("SESSDATA.expires", summary["details"][0]["message"])
        self.assertEqual(stored["managed"]["refresh_status"], "not_needed")

    async def test_refresh_expiring_cookies_skips_missing_sessdata_expires(self) -> None:
        doc = await self.repo.get("9001")
        raw = doc["raw"]
        raw["cookie_info"]["cookies"] = [
            cookie for cookie in raw["cookie_info"]["cookies"]
            if cookie["name"] != "SESSDATA"
        ]
        doc["raw"] = raw
        (self.cookie_dir / "9001.json").write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")

        summary = await self.service.refresh_expiring_cookies(30 * 86400)
        stored = await self.repo.get("9001")

        self.assertEqual(summary["total"], 1)
        self.assertEqual(summary["refreshed"], 0)
        self.assertEqual(summary["skipped"], 1)
        self.assertIn("SESSDATA.expires", summary["details"][0]["message"])
        self.assertEqual(stored["managed"]["refresh_status"], "not_needed")

    async def test_get_sessdata_expires_rejects_bool(self) -> None:
        raw = build_raw("9002")
        for cookie in raw["cookie_info"]["cookies"]:
            if cookie["name"] == "SESSDATA":
                cookie["expires"] = True
                break

        self.assertIsNone(CookieService._get_sessdata_expires(raw))

    async def test_check_cookie_rebuilds_legacy_bnut_header_when_disabled(self) -> None:
        doc = await self.repo.get("9001")
        doc["managed"]["header_string"] = f"{doc['managed']['header_string']}; b_nut=legacy-nut"
        (self.cookie_dir / "9001.json").write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")

        checked = await self.service.check_cookie("9001")
        stored = await self.repo.get("9001")

        self.assertIsNotNone(checked)
        self.assertNotIn("b_nut=", checked["managed"]["header_string"])
        self.assertNotIn("b_nut=", stored["managed"]["header_string"])

    async def test_risk_control_exception_records_error_and_preserves_state(self) -> None:
        await self.repo.update_risk_control("9001", checked_ok=True, risk_controlled=True, voucher="old-voucher")
        self.service.config.bili.risk_control_enabled = True
        self.service.client = RaisingRiskClient()

        summary = await self.service.check_risk_control_for_all()
        stored = await self.repo.get("9001")

        self.assertEqual(summary["checked"], 0)
        self.assertEqual(summary["failed"], 1)
        self.assertTrue(stored["managed"]["risk_controlled"])
        self.assertEqual(stored["managed"]["risk_control_voucher"], "old-voucher")
        self.assertEqual(stored["managed"]["risk_control_error_message"], "risk boom")

    async def test_ticket_refresh_continues_when_b_nut_is_none(self) -> None:
        """fetch_b_nut 返回 None 时仍继续获取 ticket。"""
        async def fake_none_bnut(_hs: str):
            return None
        async def fake_ticket(_csrf: str = ""):
            return {"ticket": "got-it", "created_at": 1, "ttl": 1, "expires": 2}
        self.client.fetch_b_nut = fake_none_bnut
        self.client.get_bili_ticket = fake_ticket
        self.repo.bili_ticket_enabled = True
        self.service.config.bili.bili_ticket_enabled = True

        doc = await self.service.enrich_after_create("9001")
        self.assertIsNotNone(doc)
        # 应仍能写入 ticket
        raw = doc.get("raw", {})
        cookie_map = self.repo._extract_cookie_map(raw)
        self.assertEqual(cookie_map.get("bili_ticket"), "got-it")


class BilibiliClientContractTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.client = BilibiliClient()

    async def asyncTearDown(self) -> None:
        await self.client.aclose()

    async def test_risk_control_non_2xx_is_failure(self) -> None:
        self.client._get_wbi_keys = fake_wbi_keys
        self.client._client = FakeHttpClient(httpx.Response(
            500,
            headers={},
            request=httpx.Request("GET", "https://example.test"),
        ))

        result = await self.client.check_risk_control("SESSDATA=test")
        self.assertFalse(result["ok"])
        self.assertFalse(result["risk_controlled"])
        self.assertEqual(result["status"], 500)
        self.assertIn("HTTP 500", result["error_message"])

    async def test_risk_control_minus_352_without_voucher_is_controlled(self) -> None:
        self.client._get_wbi_keys = fake_wbi_keys
        self.client._client = FakeHttpClient(httpx.Response(
            200,
            headers={"bili-status-code": "-352"},
            request=httpx.Request("GET", "https://example.test"),
        ))

        result = await self.client.check_risk_control("SESSDATA=test")
        self.assertTrue(result["ok"])
        self.assertTrue(result["risk_controlled"])
        self.assertIsNone(result["voucher"])

    async def test_get_bili_ticket_requires_positive_ttl(self) -> None:
        self.client._client = FakeHttpClient(httpx.Response(
            200,
            json={"code": 0, "data": {"ticket": "ticket", "created_at": 1700000000, "ttl": 0}},
            request=httpx.Request("POST", "https://example.test"),
        ))

        self.assertIsNone(await self.client.get_bili_ticket())

    async def test_get_bili_ticket_returns_real_expires(self) -> None:
        self.client._client = FakeHttpClient(httpx.Response(
            200,
            json={"code": 0, "data": {"ticket": "ticket", "created_at": 1700000000, "ttl": 86400}},
            request=httpx.Request("POST", "https://example.test"),
        ))

        result = await self.client.get_bili_ticket()
        self.assertEqual(result, {
            "ticket": "ticket",
            "created_at": 1700000000,
            "ttl": 86400,
            "expires": 1700086400,
        })


class ConfigSchedulerTests(unittest.TestCase):
    """配置与调度双开关联动测试。"""

    def test_cookie_refresh_scan_interval_defaults_to_six_hours(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            cookie_dir = root / "cookies"
            config_path = root / "config.json"
            config_path.write_text(json.dumps({
                "HOST": "127.0.0.1",
                "PORT": 18080,
                "STORAGE": {"cookie_dir": cookie_dir.as_posix()},
                "SCHEDULER": {
                    "COOKIE_REFRESH": {
                        "enable": True,
                        "interval_seconds": 2592000,
                    },
                },
            }), encoding="utf-8")

            config = load_config(str(config_path))

        self.assertTrue(config.scheduler.cookie_refresh.enable)
        self.assertEqual(config.scheduler.cookie_refresh.interval_seconds, 2592000)
        self.assertEqual(config.scheduler.cookie_refresh.scan_interval_seconds, 21600)

    def test_cookie_refresh_scan_interval_loads_explicit_value(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            cookie_dir = root / "cookies"
            config_path = root / "config.json"
            config_path.write_text(json.dumps({
                "HOST": "127.0.0.1",
                "PORT": 18080,
                "STORAGE": {"cookie_dir": cookie_dir.as_posix()},
                "SCHEDULER": {
                    "COOKIE_REFRESH": {
                        "enable": True,
                        "interval_seconds": 2592000,
                        "scan_interval_seconds": 3600,
                    },
                },
            }), encoding="utf-8")

            config = load_config(str(config_path))

        self.assertEqual(config.scheduler.cookie_refresh.scan_interval_seconds, 3600)

    def test_risk_check_ignores_legacy_scheduler_enable(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            cookie_dir = root / "cookies"
            config_path = root / "config.json"
            config_path.write_text(json.dumps({
                "HOST": "127.0.0.1",
                "PORT": 18080,
                "STORAGE": {"cookie_dir": cookie_dir.as_posix()},
                "SCHEDULER": {
                    "RISK_CONTROL_CHECK": {
                        "enable": False,
                        "interval_seconds": 120,
                    },
                },
                "BILI": {
                    "risk_control_enabled": True,
                },
            }), encoding="utf-8")

            config = load_config(str(config_path))

        self.assertTrue(config.bili.risk_control_enabled)
        self.assertFalse(hasattr(config.scheduler.risk_control_check, "enable"))
        self.assertEqual(config.scheduler.risk_control_check.interval_seconds, 120)

    def test_default_config_migrates_legacy_yaml_once(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            default_config = root / "data" / "config.json"
            cookie_dir = root / "cookies"
            legacy_config = root / "config.yaml"
            legacy_config.write_text(
                "\n".join([
                    "HOST: 127.0.0.1",
                    "PORT: 18080",
                    "STORAGE:",
                    f"  cookie_dir: \"{cookie_dir.as_posix()}\"",
                    "API_TOKEN:",
                    "  enable: true",
                    "  token: migrated-token",
                ]),
                encoding="utf-8",
            )

            old_default = config_loader.DEFAULT_CONFIG_FILE
            old_legacy = config_loader.LEGACY_CONFIG_FILE
            try:
                config_loader.DEFAULT_CONFIG_FILE = default_config
                config_loader.LEGACY_CONFIG_FILE = legacy_config
                with self.assertLogs("core.config.loader", level="WARNING") as logs:
                    config = load_config()
            finally:
                config_loader.DEFAULT_CONFIG_FILE = old_default
                config_loader.LEGACY_CONFIG_FILE = old_legacy

            self.assertTrue(default_config.exists())
            self.assertEqual(config.api_token.token, "migrated-token")
            self.assertEqual(config.config_path, default_config.as_posix())
            saved = json.loads(default_config.read_text(encoding="utf-8"))
            self.assertEqual(saved["API_TOKEN"]["token"], "migrated-token")
            self.assertIn(f"已迁移旧配置到: {default_config.as_posix()}", "\n".join(logs.output))

    def test_default_config_generates_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            default_config = root / "data" / "config.json"
            default_cookie_dir = root / "data" / "cookie"
            legacy_config = root / "config.yaml"
            other_cwd = root / "other-cwd"
            other_cwd.mkdir()
            (other_cwd / "config.yaml").write_text(
                "API_TOKEN:\n  enable: true\n  token: cwd-token\n",
                encoding="utf-8",
            )
            old_default = config_loader.DEFAULT_CONFIG_FILE
            old_cookie = config_loader.DEFAULT_COOKIE_DIR
            old_legacy = config_loader.LEGACY_CONFIG_FILE
            old_cwd = Path.cwd()
            try:
                config_loader.DEFAULT_CONFIG_FILE = default_config
                config_loader.DEFAULT_COOKIE_DIR = default_cookie_dir
                config_loader.LEGACY_CONFIG_FILE = legacy_config
                os.chdir(other_cwd)
                with self.assertLogs("core.config.loader", level="WARNING") as logs:
                    config = load_config()
                with self.assertNoLogs("core.config.loader", level="WARNING"):
                    reloaded = load_config()
            finally:
                os.chdir(old_cwd)
                config_loader.DEFAULT_CONFIG_FILE = old_default
                config_loader.DEFAULT_COOKIE_DIR = old_cookie
                config_loader.LEGACY_CONFIG_FILE = old_legacy

            self.assertTrue(default_config.exists())
            self.assertTrue(default_cookie_dir.exists())
            self.assertFalse((other_cwd / "data" / "config.json").exists())
            self.assertTrue(config.api_token.enable)
            self.assertTrue(config.api_token.token)
            self.assertNotEqual(config.api_token.token, "cwd-token")
            self.assertEqual(reloaded.api_token.token, config.api_token.token)

            saved = json.loads(default_config.read_text(encoding="utf-8"))
            self.assertTrue(saved["API_TOKEN"]["enable"])
            self.assertEqual(saved["API_TOKEN"]["token"], config.api_token.token)
            self.assertEqual(saved["STORAGE"]["cookie_dir"], default_cookie_dir.as_posix())
            self.assertIn(f"已生成默认配置: {default_config.as_posix()}", "\n".join(logs.output))
            self.assertIn(f"初始 API Token: {config.api_token.token}", "\n".join(logs.output))

    def test_explicit_missing_config_still_raises(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            missing_config = Path(temp_dir) / "missing.json"
            with self.assertRaises(FileNotFoundError):
                load_config(str(missing_config))

    def test_ticket_task_not_started_when_bili_switch_disabled(self) -> None:
        from core.config.loader import AppConfig, BiliConfig
        from core.scheduler import AppScheduler

        class TicketServiceStub:
            async def refresh_expiring_tickets(self):
                return {"ok": True, "total": 0, "refreshed": 0, "skipped": 0, "failed": 0, "details": []}

        config = AppConfig(
            bili=BiliConfig(bili_ticket_enabled=False, risk_control_enabled=False),
        )
        scheduler = AppScheduler(service=TicketServiceStub(), config=config)

        async def run() -> None:
            app = type("AppStub", (), {"state": type("StateStub", (), {})()})()
            await scheduler.start(app)
            self.assertEqual(len(scheduler._tasks), 0)
            await scheduler.stop()

        asyncio.run(run())

    def test_ticket_task_starts_from_bili_switch_only(self) -> None:
        from core.config.loader import build_config
        from core.scheduler import AppScheduler

        class TicketServiceStub:
            async def refresh_expiring_tickets(self):
                return {"ok": True, "total": 0, "refreshed": 0, "skipped": 0, "failed": 0, "details": []}

        config = build_config({
            "SCHEDULER": {
                "BILI_TICKET_REFRESH": {
                    "enable": False,
                    "interval_seconds": 60,
                },
            },
            "BILI": {
                "bili_ticket_enabled": True,
            },
        })
        scheduler = AppScheduler(service=TicketServiceStub(), config=config)

        async def run() -> None:
            app = type("AppStub", (), {"state": type("StateStub", (), {})()})()
            await scheduler.start(app)
            self.assertEqual(len(scheduler._tasks), 1)
            await scheduler.stop()

        self.assertFalse(hasattr(config.scheduler.bili_ticket_refresh, "enable"))
        self.assertEqual(config.scheduler.bili_ticket_refresh.interval_seconds, 60)
        asyncio.run(run())

    def test_risk_task_not_started_when_bili_switch_disabled(self) -> None:
        from core.config.loader import AppConfig, BiliConfig
        from core.scheduler import AppScheduler

        class RiskServiceStub:
            async def check_risk_control_for_all(self):
                return {"ok": True, "total": 0, "checked": 0, "failed": 0, "details": []}

        config = AppConfig(
            bili=BiliConfig(bili_ticket_enabled=False, risk_control_enabled=False),
        )
        scheduler = AppScheduler(service=RiskServiceStub(), config=config)

        async def run() -> None:
            app = type("AppStub", (), {"state": type("StateStub", (), {})()})()
            await scheduler.start(app)
            self.assertEqual(len(scheduler._tasks), 0)
            await scheduler.stop()

        asyncio.run(run())

    def test_risk_task_starts_from_bili_switch_only(self) -> None:
        from core.config.loader import AppConfig, BiliConfig, SchedulerConfig, SchedulerIntervalConfig
        from core.scheduler import AppScheduler

        class RiskServiceStub:
            async def check_risk_control_for_all(self):
                return {"ok": True, "total": 0, "checked": 0, "failed": 0, "details": []}

        config = AppConfig(
            bili=BiliConfig(bili_ticket_enabled=False, risk_control_enabled=True),
            scheduler=SchedulerConfig(
                risk_control_check=SchedulerIntervalConfig(interval_seconds=60),
            ),
        )
        scheduler = AppScheduler(service=RiskServiceStub(), config=config)

        async def run() -> None:
            app = type("AppStub", (), {"state": type("StateStub", (), {})()})()
            await scheduler.start(app)
            self.assertEqual(len(scheduler._tasks), 1)
            await scheduler.stop()

        asyncio.run(run())


class MigrationScriptTests(unittest.TestCase):
    def test_build_v2_like_raw_extracts_mid_from_token_or_cookie(self) -> None:
        module = load_migrate_module()

        from_token = module._build_v2_like_raw(
            {
                "token_info": {"mid": "7001"},
                "cookie_info": {"cookies": [{"name": "DedeUserID", "value": "7999"}]},
            }
        )
        self.assertEqual(from_token["mid"], 7001)

        from_cookie = module._build_v2_like_raw(
            {
                "token_info": {},
                "cookie_info": {"cookies": [{"name": "DedeUserID", "value": "7002"}]},
            }
        )
        self.assertEqual(from_cookie["mid"], 7002)

    def test_migrate_outputs_current_managed_structure(self) -> None:
        module = load_migrate_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            src_dir = root / "src"
            dst_dir = root / "dst"
            src_dir.mkdir(parents=True, exist_ok=True)
            legacy_uid = "5001"
            legacy_path = src_dir / f"{legacy_uid}.json"
            legacy_path.write_text(
                json.dumps(build_legacy_raw(legacy_uid), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            expected_join_time = module._file_time_iso(legacy_path)

            result = asyncio.run(
                module.migrate(
                    src_dir=src_dir,
                    dst_dir=dst_dir,
                    ids=None,
                    dry_run=False,
                    overwrite=True,
                    conform_raw=True,
                )
            )

            self.assertTrue(result["ok"])
            self.assertEqual(result["migrated"], 1)

            migrated_doc = json.loads((dst_dir / f"{legacy_uid}.json").read_text(encoding="utf-8"))
            managed = migrated_doc["managed"]
            self.assertEqual(managed["DedeUserID"], legacy_uid)
            self.assertEqual(managed["join_time"], expected_join_time)
            self.assertEqual(managed["tags"], [])
            self.assertTrue(managed["header_string"].startswith("SESSDATA="))
            self.assertEqual(managed["status"], "valid")
            self.assertEqual(managed["username"], f"旧用户{legacy_uid}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
