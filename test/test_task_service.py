from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock

from cryptography.fernet import Fernet


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "BilibiliCookieMgmt"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.config.loader import AppConfig
from core.database import Database, migrate_database
from core.infrastructure.repositories import CookieRepository, TaskRepository
from core.services import CookieService, TaskService


class InspectClient:
    def __init__(self) -> None:
        self.active = 0
        self.max_active = 0

    async def inspect_cookie(self, header: str):
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        await asyncio.sleep(0.05)
        self.active -= 1
        if "network" in header:
            return {
                "status": "failed",
                "is_valid": False,
                "code": 502,
                "message": "网络错误",
                "username": None,
            }
        if "invalid" in header:
            return {
                "status": "invalid",
                "is_valid": False,
                "code": 200,
                "message": "Cookie 无效",
                "username": None,
            }
        return {
            "status": "valid",
            "is_valid": True,
            "code": 0,
            "message": "ok",
            "username": "测试用户",
        }


class TaskServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.database = Database(root / "data.db")
        await migrate_database(self.database)
        self.task_repo = TaskRepository(self.database)
        self.client = InspectClient()
        self.cookie_service = CookieService(
            CookieRepository(str(root / "cookie")),
            AppConfig(),
            bilibili_client=self.client,
        )
        self.cipher = Fernet(Fernet.generate_key())
        self.service = TaskService(self.task_repo, self.cookie_service, self.cipher)
        await self.service.start()

    async def asyncTearDown(self) -> None:
        await self.service.stop()
        await self.database.close()
        self.temp_dir.cleanup()

    async def test_raw_validation_records_each_outcome_and_encrypts_source(self) -> None:
        cookies = [
            "SESSDATA=good; DedeUserID=1001",
            "SESSDATA=invalid; DedeUserID=1002",
            "SESSDATA=network; DedeUserID=1003",
        ]
        task = await self.service.create({
            "type": "raw_cookie_validation",
            "items": [
                {"line_number": index + 1, "cookie": cookie}
                for index, cookie in enumerate(cookies)
            ],
        })
        finished = await self.service.wait(task["id"])

        self.assertEqual(finished["status"], "completed_with_errors")
        self.assertEqual(finished["succeeded"], 1)
        self.assertEqual(finished["invalid"], 1)
        self.assertEqual(finished["failed"], 1)
        self.assertLessEqual(self.client.max_active, 4)
        database_bytes = self.database.path.read_bytes()
        for cookie in cookies:
            self.assertNotIn(cookie.encode("utf-8"), database_bytes)

        failed = await self.task_repo.failed_items(task["id"])
        self.assertEqual(len(failed), 1)
        self.assertIsNotNone(failed[0]["secret_payload"])
        visible = await self.task_repo.list_items(task["id"])
        self.assertTrue(all("secret_payload" not in item for item in visible["items"]))

    async def test_raw_validation_uses_four_workers(self) -> None:
        task = await self.service.create({
            "type": "raw_cookie_validation",
            "items": [
                {"line_number": index + 1, "cookie": f"SESSDATA=good-{index}; DedeUserID={index}"}
                for index in range(12)
            ],
        })
        await self.service.wait(task["id"])
        self.assertEqual(self.client.max_active, 4)

    async def test_retry_moves_failed_secret_to_child_task(self) -> None:
        task = await self.service.create({
            "type": "raw_cookie_validation",
            "items": [{"line_number": 1, "cookie": "SESSDATA=network; DedeUserID=1003"}],
        })
        await self.service.wait(task["id"])

        child = await self.service.retry_failed(task["id"])
        parent_failed = await self.task_repo.failed_items(task["id"])
        self.assertIsNone(parent_failed[0]["secret_payload"])
        await self.service.wait(child["id"])
        child_failed = await self.task_repo.failed_items(child["id"])
        self.assertIsNotNone(child_failed[0]["secret_payload"])

        with self.assertRaisesRegex(ValueError, "已转移"):
            await self.service.retry_failed(task["id"])

    async def test_manual_risk_task_is_supported(self) -> None:
        task = await self.service.create({
            "type": "risk_control_check",
            "ids": ["missing-account"],
        })
        finished = await self.service.wait(task["id"])

        self.assertEqual(finished["type"], "risk_control_check")
        self.assertEqual(finished["skipped"], 1)

    async def test_pending_task_is_recovered_after_restart(self) -> None:
        await self.service.stop()
        cookie = "SESSDATA=good; DedeUserID=9001"
        task = await self.task_repo.create_task(
            "raw_cookie_validation",
            "manual",
            [{"position": 0, "line_number": 1, "secret_payload": self.cipher.encrypt(cookie.encode())}],
        )
        self.service = TaskService(self.task_repo, self.cookie_service, self.cipher)
        await self.service.start()

        finished = await self.service.wait(task["id"])
        self.assertEqual(finished["status"], "completed")
        self.assertEqual(finished["succeeded"], 1)

    async def test_cancel_clears_pending_cookie_secrets(self) -> None:
        task = await self.service.create({
            "type": "raw_cookie_validation",
            "items": [
                {"line_number": index + 1, "cookie": f"SESSDATA=good-{index}; DedeUserID={index}"}
                for index in range(40)
            ],
        })
        await asyncio.sleep(0.03)
        await self.service.cancel(task["id"])
        finished = await self.service.wait(task["id"])

        self.assertEqual(finished["status"], "cancelled")
        self.assertGreater(finished["cancelled"], 0)
        items = await self.task_repo.list_items(task["id"], page_size=100, include_secret=True)
        cancelled = [item for item in items["items"] if item["status"] == "cancelled"]
        self.assertTrue(cancelled)
        self.assertTrue(all(item["secret_payload"] is None for item in cancelled))

    async def test_cancelled_items_can_be_read_across_revision_pages(self) -> None:
        await self.service.stop()
        task = await self.task_repo.create_task(
            "cookie_check",
            "manual",
            [
                {"position": index, "subject_id": str(index)}
                for index in range(1200)
            ],
        )

        await self.task_repo.cancel_pending_items(task["id"])
        revisions = []
        after = 0
        while True:
            updates = await self.task_repo.updates(task["id"], after, limit=500)
            revisions.extend(item["revision"] for item in updates["items"])
            after = updates["next_revision"]
            if not updates["has_more"]:
                break

        self.assertEqual(revisions, list(range(1, 1201)))

    async def test_wrong_key_blocks_start_when_failed_secret_exists(self) -> None:
        task = await self.service.create({
            "type": "raw_cookie_validation",
            "items": [{"line_number": 1, "cookie": "SESSDATA=network; DedeUserID=1003"}],
        })
        await self.service.wait(task["id"])
        await self.service.stop()

        wrong_key_service = TaskService(
            self.task_repo,
            self.cookie_service,
            Fernet(Fernet.generate_key()),
        )
        with self.assertRaisesRegex(RuntimeError, "无法解密"):
            await wrong_key_service.start()

    async def test_task_level_error_finishes_unfinished_items(self) -> None:
        await self.service.stop()
        cookie = "SESSDATA=good; DedeUserID=9002"
        task = await self.task_repo.create_task(
            "raw_cookie_validation",
            "manual",
            [{"position": 0, "line_number": 1, "secret_payload": self.cipher.encrypt(cookie.encode())}],
        )
        original_pending_items = self.task_repo.pending_items
        self.task_repo.pending_items = AsyncMock(side_effect=RuntimeError("读取队列失败"))
        self.service = TaskService(self.task_repo, self.cookie_service, self.cipher)
        await self.service.start()
        finished = await self.service.wait(task["id"])
        self.task_repo.pending_items = original_pending_items

        self.assertEqual(finished["status"], "failed")
        self.assertEqual(finished["failed"], 1)
        items = await self.task_repo.list_items(task["id"], include_secret=True)
        self.assertEqual(items["items"][0]["status"], "failed")
        self.assertIsNotNone(items["items"][0]["secret_payload"])

    async def test_worker_error_waits_for_started_items_before_task_finishes(self) -> None:
        original_finish_item = self.task_repo.finish_item
        failed_once = False

        async def flaky_finish_item(item_id, status, result):
            nonlocal failed_once
            if not failed_once:
                failed_once = True
                raise RuntimeError("结果写入失败")
            await original_finish_item(item_id, status, result)

        self.task_repo.finish_item = flaky_finish_item
        task = await self.service.create({
            "type": "raw_cookie_validation",
            "items": [
                {"line_number": index + 1, "cookie": f"SESSDATA=good-{index}; DedeUserID={index}"}
                for index in range(8)
            ],
        })
        finished = await self.service.wait(task["id"])
        self.task_repo.finish_item = original_finish_item

        self.assertEqual(finished["status"], "failed")
        self.assertEqual(finished["succeeded"] + finished["failed"], finished["total"])
        items = await self.task_repo.list_items(task["id"], page_size=20)
        self.assertTrue(all(item["status"] in {"succeeded", "failed"} for item in items["items"]))

    async def test_cleanup_deletes_only_expired_terminal_tasks(self) -> None:
        task = await self.service.create({
            "type": "raw_cookie_validation",
            "items": [{"line_number": 1, "cookie": "SESSDATA=good; DedeUserID=1"}],
        })
        await self.service.wait(task["id"])
        old_time = (datetime.now(timezone.utc) - timedelta(days=31)).isoformat()
        await self.database.connection.execute(
            "UPDATE tasks SET completed_at = ? WHERE id = ?", (old_time, task["id"])
        )
        await self.database.connection.commit()

        self.assertEqual(await self.task_repo.cleanup(30), 1)
        self.assertIsNone(await self.task_repo.get_task(task["id"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
