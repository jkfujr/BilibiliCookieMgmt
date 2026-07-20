from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional
from uuid import uuid4

import aiosqlite

from ...database import Database


TERMINAL_TASK_STATUSES = {"completed", "completed_with_errors", "cancelled", "failed"}
TERMINAL_ITEM_STATUSES = {"succeeded", "invalid", "failed", "skipped", "cancelled"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


class TaskRepository:
    def __init__(self, database: Database):
        if database.connection is None:
            raise RuntimeError("数据库尚未打开")
        self.database = database
        self.connection = database.connection
        self._write_lock = asyncio.Lock()

    @staticmethod
    def _task_dict(row, item_counts: Optional[Dict[str, int]] = None) -> Dict[str, Any]:
        task = dict(row)
        task["payload"] = json.loads(task.pop("payload_json") or "{}")
        task["cancel_requested"] = bool(task["cancel_requested"])
        counts = item_counts or {}
        task["pending"] = counts.get("pending", 0)
        task["running"] = counts.get("running", 0)
        return task

    @staticmethod
    def _item_dict(row, include_secret: bool = False) -> Dict[str, Any]:
        item = dict(row)
        item["input"] = json.loads(item.pop("input_json") or "{}")
        item["result"] = json.loads(item.pop("result_json") or "{}")
        if not include_secret:
            item.pop("secret_payload", None)
        return item

    async def create_task(
        self,
        task_type: str,
        source: str,
        items: Iterable[Dict[str, Any]],
        *,
        payload: Optional[Dict[str, Any]] = None,
        parent_task_id: Optional[str] = None,
        clear_secret_item_ids: Iterable[int] = (),
    ) -> Dict[str, Any]:
        task_id = uuid4().hex
        item_list = list(items)
        secret_item_ids = [int(item_id) for item_id in clear_secret_item_ids]
        timestamp = _now()
        async with self._write_lock:
            await self.connection.execute("BEGIN IMMEDIATE")
            try:
                await self.connection.execute(
                    """
                    INSERT INTO tasks(
                        id, type, source, status, parent_task_id, payload_json,
                        total, created_at, updated_at
                    ) VALUES (?, ?, ?, 'queued', ?, ?, ?, ?, ?)
                    """,
                    (
                        task_id,
                        task_type,
                        source,
                        parent_task_id,
                        _json(payload or {}),
                        len(item_list),
                        timestamp,
                        timestamp,
                    ),
                )
                for index, item in enumerate(item_list):
                    await self.connection.execute(
                        """
                        INSERT INTO task_items(
                            task_id, position, line_number, subject_id, status,
                            input_json, secret_payload, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, 'pending', ?, ?, ?, ?)
                        """,
                        (
                            task_id,
                            int(item.get("position", index)),
                            item.get("line_number"),
                            item.get("subject_id"),
                            _json(item.get("input") or {}),
                            item.get("secret_payload"),
                            timestamp,
                            timestamp,
                        ),
                    )
                if secret_item_ids:
                    placeholders = ",".join("?" for _ in secret_item_ids)
                    await self.connection.execute(
                        f"UPDATE task_items SET secret_payload = NULL WHERE id IN ({placeholders})",
                        secret_item_ids,
                    )
                await self.connection.commit()
            except aiosqlite.IntegrityError as exc:
                await self.connection.rollback()
                if parent_task_id:
                    raise ValueError("该任务已创建重试子任务") from exc
                raise
            except Exception:
                await self.connection.rollback()
                raise
        task = await self.get_task(task_id)
        if task is None:
            raise RuntimeError(f"任务创建后无法读取: {task_id}")
        return task

    async def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        cursor = await self.connection.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
        row = await cursor.fetchone()
        if row is None:
            return None
        count_cursor = await self.connection.execute(
            "SELECT status, COUNT(*) AS count FROM task_items WHERE task_id = ? GROUP BY status",
            (task_id,),
        )
        counts = {str(item["status"]): int(item["count"]) for item in await count_cursor.fetchall()}
        return self._task_dict(row, counts)

    async def list_tasks(
        self,
        *,
        page: int = 1,
        page_size: int = 25,
        status: Optional[str] = None,
        task_type: Optional[str] = None,
        source: Optional[str] = None,
    ) -> Dict[str, Any]:
        filters: List[str] = []
        values: List[Any] = []
        for column, value in (("status", status), ("type", task_type), ("source", source)):
            if value:
                filters.append(f"{column} = ?")
                values.append(value)
        where = f" WHERE {' AND '.join(filters)}" if filters else ""
        count_cursor = await self.connection.execute(f"SELECT COUNT(*) AS count FROM tasks{where}", values)
        count_row = await count_cursor.fetchone()
        if count_row is None:
            raise RuntimeError("无法读取任务总数")
        total = int(count_row["count"])
        offset = (page - 1) * page_size
        cursor = await self.connection.execute(
            f"SELECT * FROM tasks{where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
            [*values, page_size, offset],
        )
        return {
            "items": [self._task_dict(row) for row in await cursor.fetchall()],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    async def list_items(
        self,
        task_id: str,
        *,
        page: int = 1,
        page_size: int = 50,
        status: Optional[str] = None,
        include_secret: bool = False,
    ) -> Dict[str, Any]:
        where = "task_id = ?"
        values: List[Any] = [task_id]
        if status:
            where += " AND status = ?"
            values.append(status)
        count_cursor = await self.connection.execute(
            f"SELECT COUNT(*) AS count FROM task_items WHERE {where}", values
        )
        count_row = await count_cursor.fetchone()
        if count_row is None:
            raise RuntimeError("无法读取任务明细总数")
        total = int(count_row["count"])
        cursor = await self.connection.execute(
            f"SELECT * FROM task_items WHERE {where} ORDER BY position LIMIT ? OFFSET ?",
            [*values, page_size, (page - 1) * page_size],
        )
        return {
            "items": [self._item_dict(row, include_secret) for row in await cursor.fetchall()],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    async def updates(self, task_id: str, after_revision: int, limit: int = 500) -> Dict[str, Any]:
        cursor = await self.connection.execute(
            """
            SELECT * FROM task_items
            WHERE task_id = ? AND revision > ?
            ORDER BY revision
            LIMIT ?
            """,
            (task_id, after_revision, limit),
        )
        items = [self._item_dict(row) for row in await cursor.fetchall()]
        task = await self.get_task(task_id)
        return {
            "task": task,
            "items": items,
            "next_revision": max([after_revision, *[int(item["revision"]) for item in items]]),
            "has_more": bool(task and items and int(items[-1]["revision"]) < int(task["revision"])),
        }

    async def recover_unfinished(self) -> List[str]:
        async with self._write_lock:
            await self.connection.execute("BEGIN IMMEDIATE")
            try:
                timestamp = _now()
                await self.connection.execute(
                    "UPDATE task_items SET status = 'pending', started_at = NULL, updated_at = ? WHERE status = 'running'",
                    (timestamp,),
                )
                await self.connection.execute(
                    "UPDATE tasks SET status = 'queued', started_at = NULL, updated_at = ? WHERE status IN ('running', 'queued', 'cancelling')",
                    (timestamp,),
                )
                cursor = await self.connection.execute(
                    "SELECT id FROM tasks WHERE status = 'queued' ORDER BY created_at"
                )
                task_ids = [str(row["id"]) for row in await cursor.fetchall()]
                await self.connection.commit()
            except Exception:
                await self.connection.rollback()
                raise
        return task_ids

    async def set_running(self, task_id: str) -> None:
        timestamp = _now()
        async with self._write_lock:
            await self.connection.execute(
                "UPDATE tasks SET status = 'running', started_at = COALESCE(started_at, ?), updated_at = ? WHERE id = ?",
                (timestamp, timestamp, task_id),
            )
            await self.connection.commit()

    async def pending_items(self, task_id: str, include_secret: bool = True) -> List[Dict[str, Any]]:
        cursor = await self.connection.execute(
            "SELECT * FROM task_items WHERE task_id = ? AND status = 'pending' ORDER BY position",
            (task_id,),
        )
        return [self._item_dict(row, include_secret) for row in await cursor.fetchall()]

    async def set_item_running(self, item_id: int) -> bool:
        async with self._write_lock:
            cursor = await self.connection.execute(
                """
                UPDATE task_items SET status = 'running', started_at = ?, updated_at = ?
                WHERE id = ? AND status = 'pending'
                    AND EXISTS (
                        SELECT 1 FROM tasks
                        WHERE tasks.id = task_items.task_id AND tasks.cancel_requested = 0
                    )
                """,
                (_now(), _now(), item_id),
            )
            await self.connection.commit()
            return cursor.rowcount == 1

    async def finish_item(self, item_id: int, status: str, result: Dict[str, Any]) -> None:
        if status not in TERMINAL_ITEM_STATUSES:
            raise ValueError("任务项终态非法")
        count_column = status if status != "succeeded" else "succeeded"
        clear_secret = status != "failed"
        async with self._write_lock:
            await self.connection.execute("BEGIN IMMEDIATE")
            try:
                row_cursor = await self.connection.execute(
                    "SELECT task_id FROM task_items WHERE id = ?", (item_id,)
                )
                row = await row_cursor.fetchone()
                if row is None:
                    raise KeyError(f"任务项不存在: {item_id}")
                task_id = str(row["task_id"])
                timestamp = _now()
                await self.connection.execute(
                    f"UPDATE tasks SET {count_column} = {count_column} + 1, revision = revision + 1, updated_at = ? WHERE id = ?",
                    (timestamp, task_id),
                )
                revision_cursor = await self.connection.execute(
                    "SELECT revision FROM tasks WHERE id = ?", (task_id,)
                )
                revision_row = await revision_cursor.fetchone()
                if revision_row is None:
                    raise RuntimeError(f"任务不存在: {task_id}")
                revision = int(revision_row["revision"])
                await self.connection.execute(
                    """
                    UPDATE task_items
                    SET status = ?, result_json = ?, revision = ?, completed_at = ?, updated_at = ?,
                        secret_payload = CASE WHEN ? THEN NULL ELSE secret_payload END
                    WHERE id = ?
                    """,
                    (status, _json(result), revision, timestamp, timestamp, clear_secret, item_id),
                )
                await self.connection.commit()
            except Exception:
                await self.connection.rollback()
                raise

    async def request_cancel(self, task_id: str) -> Optional[Dict[str, Any]]:
        task = await self.get_task(task_id)
        if not task or task["status"] in TERMINAL_TASK_STATUSES:
            return task
        async with self._write_lock:
            await self.connection.execute(
                "UPDATE tasks SET cancel_requested = 1, status = 'cancelling', updated_at = ? WHERE id = ?",
                (_now(), task_id),
            )
            await self.connection.commit()
        return await self.get_task(task_id)

    async def cancel_requested(self, task_id: str) -> bool:
        cursor = await self.connection.execute("SELECT cancel_requested FROM tasks WHERE id = ?", (task_id,))
        row = await cursor.fetchone()
        return bool(row and row["cancel_requested"])

    async def cancel_pending_items(self, task_id: str) -> None:
        async with self._write_lock:
            await self.connection.execute("BEGIN IMMEDIATE")
            try:
                item_cursor = await self.connection.execute(
                    "SELECT id FROM task_items WHERE task_id = ? AND status = 'pending' ORDER BY position",
                    (task_id,),
                )
                item_ids = [int(row["id"]) for row in await item_cursor.fetchall()]
                count = len(item_ids)
                timestamp = _now()
                if count:
                    revision_cursor = await self.connection.execute(
                        "SELECT revision FROM tasks WHERE id = ?", (task_id,)
                    )
                    revision_row = await revision_cursor.fetchone()
                    if revision_row is None:
                        raise RuntimeError(f"任务不存在: {task_id}")
                    base_revision = int(revision_row["revision"])
                    await self.connection.execute(
                        "UPDATE tasks SET cancelled = cancelled + ?, revision = revision + ?, updated_at = ? WHERE id = ?",
                        (count, count, timestamp, task_id),
                    )
                    await self.connection.executemany(
                        """
                        UPDATE task_items SET status = 'cancelled', secret_payload = NULL,
                            result_json = '{"message":"任务已取消"}', revision = ?,
                            completed_at = ?, updated_at = ?
                        WHERE id = ? AND status = 'pending'
                        """,
                        [
                            (base_revision + offset, timestamp, timestamp, item_id)
                            for offset, item_id in enumerate(item_ids, start=1)
                        ],
                    )
                await self.connection.commit()
            except Exception:
                await self.connection.rollback()
                raise

    async def fail_unfinished_items(self, task_id: str, message: str) -> None:
        """任务级异常时收束未完成明细，并保留失败项密文供重试。"""
        async with self._write_lock:
            await self.connection.execute("BEGIN IMMEDIATE")
            try:
                item_cursor = await self.connection.execute(
                    """
                    SELECT id FROM task_items
                    WHERE task_id = ? AND status IN ('pending', 'running')
                    ORDER BY position
                    """,
                    (task_id,),
                )
                item_ids = [int(row["id"]) for row in await item_cursor.fetchall()]
                if item_ids:
                    revision_cursor = await self.connection.execute(
                        "SELECT revision FROM tasks WHERE id = ?", (task_id,)
                    )
                    revision_row = await revision_cursor.fetchone()
                    if revision_row is None:
                        raise RuntimeError(f"任务不存在: {task_id}")
                    base_revision = int(revision_row["revision"])
                    timestamp = _now()
                    await self.connection.execute(
                        "UPDATE tasks SET failed = failed + ?, revision = revision + ?, updated_at = ? WHERE id = ?",
                        (len(item_ids), len(item_ids), timestamp, task_id),
                    )
                    await self.connection.executemany(
                        """
                        UPDATE task_items SET status = 'failed', result_json = ?, revision = ?,
                            completed_at = ?, updated_at = ?
                        WHERE id = ? AND status IN ('pending', 'running')
                        """,
                        [
                            (_json({"message": message}), base_revision + offset, timestamp, timestamp, item_id)
                            for offset, item_id in enumerate(item_ids, start=1)
                        ],
                    )
                await self.connection.commit()
            except Exception:
                await self.connection.rollback()
                raise

    async def first_secret_payload(self) -> Optional[bytes]:
        cursor = await self.connection.execute(
            "SELECT secret_payload FROM task_items WHERE secret_payload IS NOT NULL LIMIT 1"
        )
        row = await cursor.fetchone()
        return bytes(row["secret_payload"]) if row is not None else None

    async def finish_task(self, task_id: str, error_message: Optional[str] = None) -> Dict[str, Any]:
        task = await self.get_task(task_id)
        if task is None:
            raise KeyError(f"任务不存在: {task_id}")
        if error_message:
            status = "failed"
        elif task["cancel_requested"]:
            status = "cancelled"
        elif int(task["failed"]) > 0:
            status = "completed_with_errors"
        else:
            status = "completed"
        async with self._write_lock:
            await self.connection.execute(
                """
                UPDATE tasks SET status = ?, error_message = ?, completed_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (status, error_message, _now(), _now(), task_id),
            )
            await self.connection.commit()
        result = await self.get_task(task_id)
        if result is None:
            raise RuntimeError(f"任务结束后无法读取: {task_id}")
        return result

    async def failed_items(self, task_id: str) -> List[Dict[str, Any]]:
        cursor = await self.connection.execute(
            "SELECT * FROM task_items WHERE task_id = ? AND status = 'failed' ORDER BY position",
            (task_id,),
        )
        return [self._item_dict(row, include_secret=True) for row in await cursor.fetchall()]

    async def delete_task(self, task_id: str) -> bool:
        task = await self.get_task(task_id)
        if not task:
            return False
        if task["status"] not in TERMINAL_TASK_STATUSES:
            raise ValueError("只能删除已结束任务")
        async with self._write_lock:
            await self.connection.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
            await self.connection.commit()
        return True

    async def cleanup(self, retention_days: Optional[int]) -> int:
        if retention_days is None:
            return 0
        cutoff = (datetime.now(timezone.utc) - timedelta(days=retention_days)).isoformat()
        placeholders = ",".join("?" for _ in TERMINAL_TASK_STATUSES)
        values = [*sorted(TERMINAL_TASK_STATUSES), cutoff]
        async with self._write_lock:
            cursor = await self.connection.execute(
                f"DELETE FROM tasks WHERE status IN ({placeholders}) AND completed_at < ?", values
            )
            await self.connection.commit()
            return max(0, cursor.rowcount)

    async def active_count(self) -> int:
        cursor = await self.connection.execute(
            "SELECT COUNT(*) AS count FROM tasks WHERE status NOT IN ('completed', 'completed_with_errors', 'cancelled', 'failed')"
        )
        count_row = await cursor.fetchone()
        if count_row is None:
            raise RuntimeError("无法读取活动任务总数")
        return int(count_row["count"])
