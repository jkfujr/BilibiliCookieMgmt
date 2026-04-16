from __future__ import annotations

import asyncio
import importlib.util
import json
import logging
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

from fastapi.testclient import TestClient


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "BilibiliCookieMgmt"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.infrastructure.repositories.cookie_repository import CookieRepository
from core.services.cookie_service import CookieService


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
    config_path.write_text(
        textwrap.dedent(
            f"""
            HOST: 127.0.0.1
            PORT: 18080
            API_TOKEN:
              enable: true
              token: test-token
            STORAGE:
              cookie_dir: "{cookie_dir.as_posix()}"
            GOTIFY:
              enable: false
            SCHEDULER:
              COOKIE_CHECK:
                enable: false
                interval_seconds: 600
              COOKIE_REFRESH:
                enable: false
                interval_seconds: 86400
            """
        ).strip(),
        encoding="utf-8",
    )


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

        updated = await self.repo.update_tags("1001", ["主力号", "直播"])
        self.assertIsNotNone(updated)
        self.assertEqual(updated["managed"]["tags"], ["主力号", "直播"])

        stored_doc = json.loads((self.cookie_dir / "1001.json").read_text(encoding="utf-8"))
        self.assertEqual(stored_doc["managed"]["tags"], ["主力号", "直播"])

        cleared = await self.repo.update_tags("1001", [])
        self.assertIsNotNone(cleared)
        self.assertEqual(cleared["managed"]["tags"], [])

    async def test_legacy_document_without_tags_is_rejected(self) -> None:
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
        (self.cookie_dir / "1002.json").write_text(json.dumps(legacy_doc, ensure_ascii=False), encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "managed.tags"):
            await self.repo.get("1002")


class ServiceTagTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.cookie_dir = Path(self.temp_dir.name) / "cookies"
        self.repo = CookieRepository(str(self.cookie_dir))
        self.service = CookieService(self.repo)
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
        self.config_path = self.root / "config.yaml"
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
        self.assertEqual(items["3002"]["managed"]["tags"], [])

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

    def test_invalid_legacy_document_is_rejected_by_api(self) -> None:
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

        error_client = TestClient(self.app, raise_server_exceptions=False)
        try:
            response = error_client.get("/api/v1/cookies/3999", headers=self.auth_headers)
        finally:
            error_client.close()

        self.assertEqual(response.status_code, 500)


class MigrationScriptTests(unittest.TestCase):
    def test_migrate_outputs_current_managed_structure(self) -> None:
        module = load_migrate_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            src_dir = root / "src"
            dst_dir = root / "dst"
            src_dir.mkdir(parents=True, exist_ok=True)
            legacy_uid = "5001"
            (src_dir / f"{legacy_uid}.json").write_text(
                json.dumps(build_legacy_raw(legacy_uid), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

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
            self.assertEqual(managed["tags"], [])
            self.assertTrue(managed["header_string"].startswith("SESSDATA="))
            self.assertEqual(managed["status"], "valid")
            self.assertEqual(managed["username"], f"旧用户{legacy_uid}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
