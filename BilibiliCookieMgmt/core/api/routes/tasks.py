from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status

from ..deps import get_task_service
from ...services.task_service import TaskService
from ...utils.security import require_api_token


router = APIRouter(prefix="/tasks", tags=["tasks"], dependencies=[Depends(require_api_token)])


@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def create_task(
    payload: Dict[str, Any] = Body(...),
    service: TaskService = Depends(get_task_service),
):
    try:
        return await service.create(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("")
async def list_tasks(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    status_filter: Optional[str] = Query(None, alias="status"),
    task_type: Optional[str] = Query(None, alias="type"),
    source: Optional[str] = None,
    service: TaskService = Depends(get_task_service),
):
    return await service.repo.list_tasks(
        page=page,
        page_size=page_size,
        status=status_filter,
        task_type=task_type,
        source=source,
    )


@router.get("/active-count")
async def active_task_count(service: TaskService = Depends(get_task_service)):
    return {"count": await service.repo.active_count()}


@router.get("/{task_id}")
async def get_task(task_id: str, service: TaskService = Depends(get_task_service)):
    task = await service.repo.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return task


@router.get("/{task_id}/items")
async def list_task_items(
    task_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    status_filter: Optional[str] = Query(None, alias="status"),
    service: TaskService = Depends(get_task_service),
):
    if not await service.repo.get_task(task_id):
        raise HTTPException(status_code=404, detail="任务不存在")
    return await service.repo.list_items(
        task_id,
        page=page,
        page_size=page_size,
        status=status_filter,
    )


@router.get("/{task_id}/updates")
async def get_task_updates(
    task_id: str,
    after_revision: int = Query(0, alias="after", ge=0),
    limit: int = Query(500, ge=1, le=1000),
    service: TaskService = Depends(get_task_service),
):
    if not await service.repo.get_task(task_id):
        raise HTTPException(status_code=404, detail="任务不存在")
    return await service.repo.updates(task_id, after_revision, limit)


@router.post("/{task_id}/cancel")
async def cancel_task(task_id: str, service: TaskService = Depends(get_task_service)):
    task = await service.cancel(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return task


@router.post("/{task_id}/retry", status_code=status.HTTP_202_ACCEPTED)
async def retry_task(task_id: str, service: TaskService = Depends(get_task_service)):
    try:
        return await service.retry_failed(task_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/{task_id}")
async def delete_task(task_id: str, service: TaskService = Depends(get_task_service)):
    try:
        deleted = await service.repo.delete_task(task_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="任务不存在")
    return {"deleted": True, "task_id": task_id}
