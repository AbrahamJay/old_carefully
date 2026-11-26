"""异常巡检路由。

全部 admin-only：队列、指标、手动扫描与三种处理动作都写审计。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ...api.deps import get_task_service, require_roles
from ...core.enums import Role
from ...db.models import User
from .schemas import (
    HandleIn,
    IgnoreIn,
    ScanResultOut,
    SnoozeIn,
    TaskListOut,
    TaskOut,
    TaskSummaryOut,
)
from .service import TaskService

router = APIRouter(tags=["异常巡检"])


@router.get("/admin/tasks/summary", response_model=TaskSummaryOut)
def task_summary(
    _: User = Depends(require_roles(Role.ADMIN)),
    service: TaskService = Depends(get_task_service),
) -> TaskSummaryOut:
    """顶部指标：待处理 / 高优先级 / 今日已处理 / 平均处理时长 / 扫描频率。"""
    return service.summary()


@router.get("/admin/tasks", response_model=TaskListOut)
def list_tasks(
    status: str | None = Query(default=None),
    task_type: str | None = Query(default=None, alias="type"),
    severity: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    _: User = Depends(require_roles(Role.ADMIN)),
    service: TaskService = Depends(get_task_service),
) -> TaskListOut:
    items, total = service.list_page(
        status=status,
        task_type=task_type,
        severity=severity,
        page=page,
        page_size=page_size,
    )
    return TaskListOut(items=items, total=total)


@router.post("/admin/tasks/scan", response_model=ScanResultOut)
def scan_tasks(
    _: User = Depends(require_roles(Role.ADMIN)),
    service: TaskService = Depends(get_task_service),
) -> ScanResultOut:
    """手动触发一次扫描：本地没起 worker 时用于验证与补救。"""
    return service.scan(trigger="manual")


@router.get("/admin/tasks/{task_id}", response_model=TaskOut)
def get_task(
    task_id: int,
    _: User = Depends(require_roles(Role.ADMIN)),
    service: TaskService = Depends(get_task_service),
) -> TaskOut:
    return service.get(task_id)


@router.post("/admin/tasks/{task_id}/handle", response_model=TaskOut)
def handle_task(
    task_id: int,
    payload: HandleIn,
    user: User = Depends(require_roles(Role.ADMIN)),
    service: TaskService = Depends(get_task_service),
) -> TaskOut:
    """标记已处理：记录操作人、时间与备注。"""
    return service.handle(user, task_id, payload.note)


@router.post("/admin/tasks/{task_id}/snooze", response_model=TaskOut)
def snooze_task(
    task_id: int,
    payload: SnoozeIn,
    user: User = Depends(require_roles(Role.ADMIN)),
    service: TaskService = Depends(get_task_service),
) -> TaskOut:
    """稍后处理：到期自动重新出现，不能永久隐藏。"""
    return service.snooze(user, task_id, payload.hours, payload.note)


@router.post("/admin/tasks/{task_id}/ignore", response_model=TaskOut)
def ignore_task(
    task_id: int,
    payload: IgnoreIn,
    user: User = Depends(require_roles(Role.ADMIN)),
    service: TaskService = Depends(get_task_service),
) -> TaskOut:
    """忽略：必须记录原因，状态置 ignored 后不再提示。"""
    return service.ignore(user, task_id, payload.reason)
