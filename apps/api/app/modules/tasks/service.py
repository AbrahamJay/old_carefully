"""异常巡检服务：扫描、队列查询与人工处理。

边界与文档一致：只提示不自动处理；「去处理」由前端跳订单页，
「稍后处理」必须带到期时间，「标记已处理 / 忽略」记录操作人、时间与备注。
"""

from __future__ import annotations

import logging
import time
from datetime import timedelta

from sqlalchemy import text
from sqlalchemy.orm import Session

from ...core.config import settings
from ...core.enums import TaskSeverity, TaskStatus
from ...core.errors import (
    BadRequestError,
    ConflictError,
    FeatureUnavailableError,
    NotFoundError,
)
from ...core.time import business_day_start_utc, utcnow
from ...db.models import AdminTask, User
from ..audit import AuditService
from .repository import TaskRepository
from .scanner import detect
from .schemas import ScanResultOut, TaskOut, TaskSummaryOut

logger = logging.getLogger(__name__)

# 全局扫描锁：多副本 worker 与手动扫描同时触发时只有一个真正执行
ANOMALY_LOCK_KEY = 728194301

_ACTIVE_STATUSES = (TaskStatus.OPEN, TaskStatus.SNOOZED)


class TaskService:
    def __init__(self, db: Session, repo: TaskRepository, audit: AuditService) -> None:
        self._db = db
        self._repo = repo
        self._audit = audit

    # ------------------------------------------------------------------ 查询
    def list_page(
        self,
        *,
        status: str | None,
        task_type: str | None,
        severity: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[TaskOut], int]:
        tasks, total = self._repo.list_page(
            status=status,
            task_type=task_type,
            severity=severity,
            offset=(page - 1) * page_size,
            limit=page_size,
        )
        return [self._to_out(task) for task in tasks], total

    def get(self, task_id: int) -> TaskOut:
        task = self._repo.get(task_id)
        if task is None:
            raise NotFoundError("任务不存在")
        return self._to_out(task)

    def summary(self) -> TaskSummaryOut:
        day_start = business_day_start_utc()
        return TaskSummaryOut(
            open=self._repo.count(TaskStatus.OPEN),
            high=self._repo.count(TaskStatus.OPEN, TaskSeverity.HIGH),
            handled_today=self._repo.handled_since(day_start),
            avg_handle_minutes=self._repo.avg_handle_minutes(day_start),
            scan_interval_minutes=settings.anomaly_scan_interval_minutes,
            scan_enabled=settings.anomaly_scan_enabled,
            last_scan_at=self._repo.last_scan_at(),
            by_type=self._repo.counts_by_type(TaskStatus.OPEN),
        )

    # ------------------------------------------------------------------ 处理
    def handle(self, actor: User, task_id: int, note: str) -> TaskOut:
        task = self._active(task_id)
        text_note = note.strip()
        if not text_note:
            raise BadRequestError("请填写处理说明")
        task.status = TaskStatus.HANDLED
        task.handled_by = actor.id
        task.handled_at = utcnow()
        task.note = text_note
        task.snoozed_until = None
        self._audit.record(
            actor.id,
            "task_handle",
            "admin_task",
            task.id,
            {"type": task.type, "order_id": task.order_id, "note": text_note},
        )
        self._db.commit()
        return self._to_out(self._reload(task.id))

    def snooze(self, actor: User, task_id: int, hours: float, note: str = "") -> TaskOut:
        task = self._active(task_id)
        until = utcnow() + timedelta(hours=hours)
        task.status = TaskStatus.SNOOZED
        task.snoozed_until = until
        task.note = note.strip() or task.note
        self._audit.record(
            actor.id,
            "task_snooze",
            "admin_task",
            task.id,
            {"type": task.type, "order_id": task.order_id, "hours": hours},
        )
        self._db.commit()
        return self._to_out(self._reload(task.id))

    def ignore(self, actor: User, task_id: int, reason: str) -> TaskOut:
        task = self._active(task_id)
        text_reason = reason.strip()
        if not text_reason:
            raise BadRequestError("请填写忽略原因")
        task.status = TaskStatus.IGNORED
        task.handled_by = actor.id
        task.handled_at = utcnow()
        task.note = text_reason
        task.snoozed_until = None
        self._audit.record(
            actor.id,
            "task_ignore",
            "admin_task",
            task.id,
            {"type": task.type, "order_id": task.order_id, "reason": text_reason},
        )
        self._db.commit()
        return self._to_out(self._reload(task.id))

    # ------------------------------------------------------------------ 扫描
    def scan(self, *, trigger: str = "manual") -> ScanResultOut:
        """跑一轮扫描：加锁 → 认领/刷新任务 → 收敛消失的任务 → 留审计。"""
        if not settings.anomaly_scan_enabled:
            raise FeatureUnavailableError("异常巡检未启用", http_status=503)

        started = time.perf_counter()
        now = utcnow()
        locked = self._db.scalar(
            text("SELECT pg_try_advisory_lock(:key)"), {"key": ANOMALY_LOCK_KEY}
        )
        if not locked:
            return ScanResultOut(scanned=False, skip_reason="另一个扫描正在进行中")

        detected = 0
        created = 0
        resolved = 0
        try:
            self._repo.reopen_expired(now)
            items = detect(self._db, now)
            detected = len(items)
            keys = [item.dedupe_key for item in items]
            existing = self._repo.existing_keys(keys)
            created = sum(1 for key in keys if key not in existing)
            self._repo.upsert(
                [
                    {
                        "type": item.type,
                        "order_id": item.order_id,
                        "severity": item.severity,
                        "dedupe_key": item.dedupe_key,
                        "title": item.title,
                        "detail": item.detail,
                        "detected_at": now,
                        "status": TaskStatus.OPEN,
                        "note": "",
                    }
                    for item in items
                ],
                now,
            )
            resolved = self._repo.resolve_stale(keys, now)
            self._audit.record(
                None,
                "anomaly_scan",
                "admin_task",
                None,
                {
                    "trigger": trigger,
                    "detected": detected,
                    "created": created,
                    "updated": detected - created,
                    "resolved": resolved,
                },
            )
            self._db.commit()
        except Exception:
            self._db.rollback()
            raise
        finally:
            try:
                self._db.execute(
                    text("SELECT pg_advisory_unlock(:key)"), {"key": ANOMALY_LOCK_KEY}
                )
                self._db.commit()
            except Exception:
                logger.exception("释放异常扫描锁失败")

        duration = int((time.perf_counter() - started) * 1000)
        logger.info(
            "异常扫描完成：trigger=%s detected=%s created=%s resolved=%s duration=%sms",
            trigger,
            detected,
            created,
            resolved,
            duration,
        )
        return ScanResultOut(
            scanned=True,
            detected=detected,
            created=created,
            updated=detected - created,
            resolved=resolved,
            duration_ms=duration,
        )

    # ------------------------------------------------------------------ 内部
    def _active(self, task_id: int) -> AdminTask:
        task = self._repo.get(task_id)
        if task is None:
            raise NotFoundError("任务不存在")
        if task.status not in _ACTIVE_STATUSES:
            raise ConflictError("任务已结束，无需再处理")
        return task

    def _reload(self, task_id: int) -> AdminTask:
        task = self._repo.get(task_id)
        if task is None:
            raise NotFoundError("任务不存在")
        return task

    @staticmethod
    def _to_out(task: AdminTask) -> TaskOut:
        order = task.order
        return TaskOut(
            id=task.id,
            type=task.type,
            severity=task.severity,
            status=task.status,
            title=task.title,
            order_id=task.order_id,
            order_no=order.order_no if order else "",
            elder_name=order.elder.name if order and order.elder else "",
            service_name=order.service.name if order and order.service else "",
            scheduled_at=order.scheduled_at if order else None,
            station_name=order.station.name if order and order.station else "",
            order_status=order.status if order else "",
            detail=task.detail or {},
            detected_at=task.detected_at,
            snoozed_until=task.snoozed_until,
            handled_by=task.handled_by,
            handled_at=task.handled_at,
            note=task.note,
            updated_at=task.updated_at,
        )
