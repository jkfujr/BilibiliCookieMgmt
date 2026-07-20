from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Any, Dict, Iterable, List, Optional

from cryptography.fernet import Fernet, InvalidToken

from ..infrastructure.repositories.cookie_repository import MANAGED_KEY
from ..infrastructure.repositories.task_repository import TaskRepository, TERMINAL_TASK_STATUSES
from .cookie_service import CookieService


logger = logging.getLogger(__name__)

RAW_COOKIE_VALIDATION = "raw_cookie_validation"
COOKIE_CHECK = "cookie_check"
COOKIE_REFRESH = "cookie_refresh"
COOKIE_ENABLED_UPDATE = "cookie_enabled_update"
COOKIE_TAG_APPEND = "cookie_tag_append"
COOKIE_DELETE = "cookie_delete"
BILI_TICKET_REFRESH = "bili_ticket_refresh"
RISK_CONTROL_CHECK = "risk_control_check"

TASK_TYPES = {
    RAW_COOKIE_VALIDATION,
    COOKIE_CHECK,
    COOKIE_REFRESH,
    COOKIE_ENABLED_UPDATE,
    COOKIE_TAG_APPEND,
    COOKIE_DELETE,
    BILI_TICKET_REFRESH,
    RISK_CONTROL_CHECK,
}

MAX_TASK_ITEMS = 5000
MAX_COOKIE_LENGTH = 8192
MAX_COOKIE_PAYLOAD_BYTES = 25 * 1024 * 1024


def _normalize_ids(values: Iterable[Any]) -> List[str]:
    result: List[str] = []
    seen = set()
    for value in values:
        item = str(value or "").strip()
        if not item or item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def _extract_dede_user_id(header: str) -> Optional[str]:
    for part in header.split(";"):
        name, separator, value = part.strip().partition("=")
        if separator and name == "DedeUserID" and value.strip():
            return value.strip()
    return None


class TaskService:
    def __init__(
        self,
        repository: TaskRepository,
        cookie_service: CookieService,
        cipher: Fernet,
    ):
        self.repo = repository
        self.cookie_service = cookie_service
        self.cipher = cipher
        self._raw_queue: asyncio.Queue[str] = asyncio.Queue()
        self._raw_dispatcher: asyncio.Task | None = None
        self._cleanup_task: asyncio.Task | None = None
        self._regular_semaphore = asyncio.Semaphore(1)
        self._runners: set[asyncio.Task] = set()
        self._completion_events: Dict[str, asyncio.Event] = {}
        self._stopping = False

    async def start(self) -> None:
        self._stopping = False
        secret_payload = await self.repo.first_secret_payload()
        if secret_payload is not None:
            try:
                self.cipher.decrypt(secret_payload)
            except InvalidToken as exc:
                raise RuntimeError("当前数据密钥无法解密数据库中的任务密文") from exc
        await self.repo.cleanup(self.cookie_service.config.tasks.history_retention_days)
        self._raw_dispatcher = asyncio.create_task(self._run_raw_queue())
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        for task_id in await self.repo.recover_unfinished():
            task = await self.repo.get_task(task_id)
            if task:
                self._schedule(task)

    async def stop(self) -> None:
        self._stopping = True
        background = [task for task in (self._raw_dispatcher, self._cleanup_task) if task]
        for task in [*background, *self._runners]:
            task.cancel()
        for task in [*background, *self._runners]:
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self._runners.clear()
        self._raw_dispatcher = None
        self._cleanup_task = None

    async def create(self, request: Dict[str, Any], source: str = "manual") -> Dict[str, Any]:
        if not isinstance(request, dict):
            raise ValueError("任务请求必须是对象")
        task_type = str(request.get("type") or "").strip()
        if task_type not in TASK_TYPES:
            raise ValueError("不支持的任务类型")

        if task_type == RAW_COOKIE_VALIDATION:
            task = await self._create_raw_validation(request, source)
        elif task_type in {
            COOKIE_CHECK,
            COOKIE_REFRESH,
            COOKIE_DELETE,
            COOKIE_TAG_APPEND,
            BILI_TICKET_REFRESH,
            RISK_CONTROL_CHECK,
        }:
            task = await self._create_id_task(task_type, request, source)
        elif task_type == COOKIE_ENABLED_UPDATE:
            task = await self._create_enabled_task(request, source)
        self._schedule(task)
        return task

    async def create_cookie_check(
        self,
        *,
        ids: Optional[List[str]] = None,
        all: bool = False,
        source: str = "manual",
    ) -> Dict[str, Any]:
        return await self.create({"type": COOKIE_CHECK, "ids": ids or [], "all": all}, source)

    async def create_cookie_refresh(
        self,
        *,
        ids: Optional[List[str]] = None,
        all: bool = False,
        source: str = "manual",
    ) -> Dict[str, Any]:
        return await self.create({"type": COOKIE_REFRESH, "ids": ids or [], "all": all}, source)

    async def _create_raw_validation(self, request: Dict[str, Any], source: str) -> Dict[str, Any]:
        raw_items = request.get("items")
        if not isinstance(raw_items, list) or not raw_items:
            raise ValueError("请提供至少一条 Cookie")
        if len(raw_items) > MAX_TASK_ITEMS:
            raise ValueError(f"单次最多校验 {MAX_TASK_ITEMS} 条 Cookie")

        total_bytes = 0
        items = []
        for index, raw_item in enumerate(raw_items):
            if not isinstance(raw_item, dict):
                raise ValueError(f"第 {index + 1} 项必须是对象")
            cookie = str(raw_item.get("cookie") or "").strip()
            if not cookie:
                raise ValueError(f"第 {index + 1} 项 Cookie 不能为空")
            if "\n" in cookie or "\r" in cookie:
                raise ValueError(f"第 {index + 1} 项包含换行，请保持一行一个 Cookie")
            if len(cookie) > MAX_COOKIE_LENGTH:
                raise ValueError(f"第 {index + 1} 项超过 {MAX_COOKIE_LENGTH} 字符")
            total_bytes += len(cookie.encode("utf-8"))
            line_number = raw_item.get("line_number", index + 1)
            if isinstance(line_number, bool) or not isinstance(line_number, int) or line_number <= 0:
                raise ValueError(f"第 {index + 1} 项行号非法")
            items.append({
                "position": index,
                "line_number": line_number,
                "subject_id": _extract_dede_user_id(cookie),
                "secret_payload": self.cipher.encrypt(cookie.encode("utf-8")),
            })
        if total_bytes > MAX_COOKIE_PAYLOAD_BYTES:
            raise ValueError("Cookie 原文总大小超过 25 MiB")
        return await self.repo.create_task(task_type=RAW_COOKIE_VALIDATION, source=source, items=items)

    async def _resolve_ids(self, request: Dict[str, Any]) -> List[str]:
        if bool(request.get("all")):
            result = []
            for doc in await self.cookie_service.repo.list():
                info = doc.get(MANAGED_KEY, {}) if isinstance(doc.get(MANAGED_KEY), dict) else {}
                if not info.get("is_enabled", True):
                    continue
                if info.get("DedeUserID"):
                    result.append(str(info["DedeUserID"]))
            return result
        ids = request.get("ids") or []
        if not isinstance(ids, list):
            raise ValueError("ids 必须是数组")
        result = _normalize_ids(ids)
        if len(result) > MAX_TASK_ITEMS:
            raise ValueError(f"单次最多处理 {MAX_TASK_ITEMS} 个账号")
        return result

    async def _create_id_task(self, task_type: str, request: Dict[str, Any], source: str) -> Dict[str, Any]:
        ids = await self._resolve_ids(request)
        if not ids:
            raise ValueError("任务没有可处理的账号")
        input_data: Dict[str, Any] = {}
        if task_type == COOKIE_TAG_APPEND:
            tags = request.get("tags") or []
            if not isinstance(tags, list):
                raise ValueError("tags 必须是数组")
            normalized_tags = _normalize_ids(tags)
            if not normalized_tags:
                raise ValueError("请提供至少一个标签")
            input_data["tags"] = normalized_tags
        items = [
            {"position": index, "subject_id": account_id, "input": dict(input_data)}
            for index, account_id in enumerate(ids)
        ]
        return await self.repo.create_task(task_type, source, items)

    async def _create_enabled_task(self, request: Dict[str, Any], source: str) -> Dict[str, Any]:
        raw_items = request.get("items")
        if not isinstance(raw_items, list) or not raw_items:
            raise ValueError("请提供账号启停目标")
        if len(raw_items) > MAX_TASK_ITEMS:
            raise ValueError(f"单次最多处理 {MAX_TASK_ITEMS} 个账号")
        items = []
        seen = set()
        for raw_item in raw_items:
            if not isinstance(raw_item, dict):
                raise ValueError("账号启停项必须是对象")
            account_id = str(raw_item.get("DedeUserID") or "").strip()
            enabled = raw_item.get("is_enabled")
            if not account_id or not isinstance(enabled, bool):
                raise ValueError("账号启停项缺少合法 DedeUserID 或 is_enabled")
            if account_id in seen:
                continue
            seen.add(account_id)
            items.append({
                "position": len(items),
                "subject_id": account_id,
                "input": {"is_enabled": enabled},
            })
        return await self.repo.create_task(COOKIE_ENABLED_UPDATE, source, items)

    async def create_scheduled_cookie_check(self) -> Optional[Dict[str, Any]]:
        ids = await self._all_account_ids()
        return await self._create_scheduled(COOKIE_CHECK, ids)

    async def create_scheduled_cookie_refresh(self, threshold_seconds: int) -> Optional[Dict[str, Any]]:
        ids = await self._all_account_ids()
        return await self._create_scheduled(
            COOKIE_REFRESH,
            ids,
            input_data={"expiring_only": True, "threshold_seconds": int(threshold_seconds)},
        )

    async def create_scheduled_ticket_refresh(self) -> Optional[Dict[str, Any]]:
        ids = await self._all_account_ids()
        return await self._create_scheduled(BILI_TICKET_REFRESH, ids)

    async def create_scheduled_risk_check(self) -> Optional[Dict[str, Any]]:
        ids = await self._all_account_ids(valid_only=True)
        return await self._create_scheduled(RISK_CONTROL_CHECK, ids)

    async def _all_account_ids(self, valid_only: bool = False) -> List[str]:
        ids = []
        for doc in await self.cookie_service.repo.list():
            info = doc.get(MANAGED_KEY, {}) if isinstance(doc.get(MANAGED_KEY), dict) else {}
            if valid_only and str(info.get("status")) != "valid":
                continue
            if info.get("DedeUserID"):
                ids.append(str(info["DedeUserID"]))
        return ids

    async def _create_scheduled(
        self,
        task_type: str,
        ids: List[str],
        input_data: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        if not ids:
            return None
        task = await self.repo.create_task(
            task_type,
            "scheduled",
            [
                {"position": index, "subject_id": account_id, "input": dict(input_data or {})}
                for index, account_id in enumerate(ids)
            ],
        )
        self._schedule(task)
        return task

    def _schedule(self, task: Dict[str, Any]) -> None:
        task_id = str(task["id"])
        self._completion_events.setdefault(task_id, asyncio.Event())
        if task["type"] == RAW_COOKIE_VALIDATION:
            self._raw_queue.put_nowait(task_id)
            return
        runner = asyncio.create_task(self._run_regular_task(task_id))
        self._runners.add(runner)
        runner.add_done_callback(self._runners.discard)

    async def _run_raw_queue(self) -> None:
        while True:
            task_id = await self._raw_queue.get()
            try:
                await self._run_task(task_id, concurrency=4)
            finally:
                self._raw_queue.task_done()

    async def _run_regular_task(self, task_id: str) -> None:
        async with self._regular_semaphore:
            await self._run_task(task_id, concurrency=1)

    async def _run_task(self, task_id: str, concurrency: int) -> None:
        try:
            await self.repo.set_running(task_id)
            queue: asyncio.Queue[Dict[str, Any]] = asyncio.Queue()
            for item in await self.repo.pending_items(task_id):
                queue.put_nowait(item)
            worker_failed = asyncio.Event()

            async def worker() -> None:
                while not queue.empty():
                    if worker_failed.is_set() or await self.repo.cancel_requested(task_id):
                        return
                    try:
                        item = queue.get_nowait()
                    except asyncio.QueueEmpty:
                        return
                    try:
                        try:
                            await self._process_item(item)
                        except Exception:
                            worker_failed.set()
                            raise
                    finally:
                        queue.task_done()

            worker_results = await asyncio.gather(
                *(worker() for _ in range(max(1, concurrency))),
                return_exceptions=True,
            )
            worker_error = next(
                (result for result in worker_results if isinstance(result, Exception)),
                None,
            )
            if worker_error is not None:
                raise worker_error
            if await self.repo.cancel_requested(task_id):
                await self.repo.cancel_pending_items(task_id)
            await self.repo.finish_task(task_id)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error(f"任务执行异常: {task_id}, {exc}", exc_info=True)
            with contextlib.suppress(Exception):
                await self.repo.fail_unfinished_items(task_id, f"任务执行异常: {exc}")
                await self.repo.finish_task(task_id, str(exc))
        finally:
            self._completion_events.setdefault(task_id, asyncio.Event()).set()

    async def _process_item(self, item: Dict[str, Any]) -> None:
        if not await self.repo.set_item_running(int(item["id"])):
            return
        try:
            status, result = await self._execute_item(item)
        except Exception as exc:
            status, result = "failed", {"message": f"执行异常: {exc}"}
        await self.repo.finish_item(int(item["id"]), status, result)

    async def _execute_item(self, item: Dict[str, Any]) -> tuple[str, Dict[str, Any]]:
        task = await self.repo.get_task(str(item["task_id"]))
        if task is None:
            return "failed", {"message": "任务不存在"}
        task_type = str(task["type"])
        account_id = str(item.get("subject_id") or "")
        input_data = item.get("input") or {}

        if task_type == RAW_COOKIE_VALIDATION:
            try:
                cookie = self.cipher.decrypt(item["secret_payload"]).decode("utf-8")
            except (InvalidToken, UnicodeDecodeError, TypeError):
                return "failed", {"message": "Cookie 密文无法解密"}
            result = await self.cookie_service.test_cookie(cookie)
            result["DedeUserID"] = account_id or _extract_dede_user_id(cookie)
            outcome = str(result.get("status") or "failed")
            return ({"valid": "succeeded", "invalid": "invalid"}.get(outcome, "failed"), result)

        if task_type == COOKIE_CHECK:
            checked = await self.cookie_service.check_cookie(account_id)
            result = {"message": checked.message or "检查完成", "DedeUserID": account_id}
            return ({"valid": "succeeded", "invalid": "invalid"}.get(checked.status, "failed"), result)

        if task_type == COOKIE_REFRESH:
            if input_data.get("expiring_only"):
                result = await self.cookie_service.refresh_cookie_if_expiring(
                    account_id, int(input_data["threshold_seconds"])
                )
                result["DedeUserID"] = account_id
                return str(result["status"]), result
            document = await self.cookie_service.refresh_cookie(account_id)
            info = document.get(MANAGED_KEY, {}) if document and isinstance(document.get(MANAGED_KEY), dict) else {}
            if info.get("refresh_status") == "success":
                return "succeeded", {"message": "刷新成功", "DedeUserID": account_id}
            return "failed", {
                "message": info.get("error_message") or "刷新失败",
                "DedeUserID": account_id,
            }

        if task_type == COOKIE_ENABLED_UPDATE:
            document = await self.cookie_service.set_enabled(account_id, bool(input_data["is_enabled"]))
            return (
                ("succeeded", {"message": "状态已更新", "DedeUserID": account_id})
                if document
                else ("failed", {"message": "Cookie 不存在", "DedeUserID": account_id})
            )

        if task_type == COOKIE_TAG_APPEND:
            document = await self.cookie_service.get_cookie(account_id)
            if not document:
                return "failed", {"message": "Cookie 不存在", "DedeUserID": account_id}
            info = document.get(MANAGED_KEY, {}) if isinstance(document.get(MANAGED_KEY), dict) else {}
            tags = _normalize_ids([*(info.get("tags") or []), *(input_data.get("tags") or [])])
            await self.cookie_service.set_tags(account_id, tags)
            return "succeeded", {"message": "标签已更新", "DedeUserID": account_id}

        if task_type == COOKIE_DELETE:
            deleted = await self.cookie_service.delete_cookie(account_id)
            return (
                ("succeeded", {"message": "已删除", "DedeUserID": account_id})
                if deleted
                else ("skipped", {"message": "账号已不存在", "DedeUserID": account_id})
            )

        if task_type == BILI_TICKET_REFRESH:
            result = await self.cookie_service.refresh_ticket_if_expiring(account_id)
            result["DedeUserID"] = account_id
            return str(result["status"]), result

        if task_type == RISK_CONTROL_CHECK:
            result = await self.cookie_service.check_risk_control(account_id)
            result["DedeUserID"] = account_id
            return str(result["status"]), result

        return "failed", {"message": "未知任务类型"}

    async def wait(self, task_id: str) -> Optional[Dict[str, Any]]:
        task = await self.repo.get_task(task_id)
        if not task:
            return None
        if task["status"] not in TERMINAL_TASK_STATUSES:
            await self._completion_events.setdefault(task_id, asyncio.Event()).wait()
        return await self.repo.get_task(task_id)

    async def cancel(self, task_id: str) -> Optional[Dict[str, Any]]:
        return await self.repo.request_cancel(task_id)

    async def retry_failed(self, task_id: str) -> Dict[str, Any]:
        task = await self.repo.get_task(task_id)
        if not task:
            raise KeyError("任务不存在")
        if task["status"] not in TERMINAL_TASK_STATUSES:
            raise ValueError("任务尚未结束")
        failed = await self.repo.failed_items(task_id)
        if not failed:
            raise ValueError("任务没有失败项")
        if task["type"] == RAW_COOKIE_VALIDATION and any(item.get("secret_payload") is None for item in failed):
            raise ValueError("失败项已转移到其他重试任务")
        child = await self.repo.create_task(
            str(task["type"]),
            "retry",
            [
                {
                    "position": index,
                    "line_number": item.get("line_number"),
                    "subject_id": item.get("subject_id"),
                    "input": item.get("input") or {},
                    "secret_payload": item.get("secret_payload"),
                }
                for index, item in enumerate(failed)
            ],
            payload=task.get("payload") or {},
            parent_task_id=task_id,
            clear_secret_item_ids=(item["id"] for item in failed),
        )
        self._schedule(child)
        return child

    async def _cleanup_loop(self) -> None:
        while True:
            await asyncio.sleep(86400)
            try:
                await self.repo.cleanup(self.cookie_service.config.tasks.history_retention_days)
            except Exception as exc:
                logger.error(f"任务历史清理失败: {exc}", exc_info=True)
