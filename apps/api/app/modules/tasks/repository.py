"""``admin_tasks`` 读写。

扫描写入用 ``INSERT ... ON CONFLICT (dedupe_key) DO UPDATE``：同一订单同一状态
只保留一条，重复扫描只刷新事实，不重复建任务。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import case, func, null, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session, selectinload

from ...core.enums import TaskSeverity, TaskStatus
from ...db.models import AdminTask, AuditLog, Order

_SEVERITY_RANK = case(
    (AdminTask.severity == TaskSeverity.HIGH, 0),
    (AdminTask.severity == TaskSeverity.MEDIUM, 1),
    else_=2,
)


def _with_order():
    return (
        selectinload(AdminTask.order).selectinload(Order.elder),
        selectinload(AdminTask.order).selectinload(Order.service),
        selectinload(AdminTask.order).selectinload(Order.station),
    )


class TaskRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    # ------------------------------------------------------------------ 读取
    def get(self, task_id: int) -> AdminTask | None:
        return self._db.scalars(
            select(AdminTask).where(AdminTask.id == task_id).options(*_with_order())
        ).first()

    def list_page(
        self,
        *,
        status: str | None,
        task_type: str | None,
        severity: str | None,
        offset: int,
        limit: int,
    ) -> tuple[list[AdminTask], int]:
        stmt = select(AdminTask)
        if status:
            stmt = stmt.where(AdminTask.status == status)
        if task_type:
            stmt = stmt.where(AdminTask.type == task_type)
        if severity:
            stmt = stmt.where(AdminTask.severity == severity)
        total = self._db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        rows = self._db.scalars(
            stmt.options(*_with_order())
            .order_by(_SEVERITY_RANK, AdminTask.detected_at)
            .offset(offset)
            .limit(limit)
        ).all()
        return list(rows), total

    def count(self, status: str | None = None, severity: str | None = None) -> int:
        stmt = select(func.count()).select_from(AdminTask)
        if status:
            stmt = stmt.where(AdminTask.status == status)
        if severity:
            stmt = stmt.where(AdminTask.severity == severity)
        return self._db.scalar(stmt) or 0

    def counts_by_type(self, status: str) -> dict[str, int]:
        rows = self._db.execute(
            select(AdminTask.type, func.count())
            .where(AdminTask.status == status)
            .group_by(AdminTask.type)
        ).all()
        return {str(task_type): int(count) for task_type, count in rows}

    def handled_since(self, start: datetime) -> int:
        return (
            self._db.scalar(
                select(func.count())
                .select_from(AdminTask)
                .where(AdminTask.status == TaskStatus.HANDLED, AdminTask.handled_at >= start)
            )
            or 0
        )

    def avg_handle_minutes(self, start: datetime) -> int:
        seconds = self._db.scalar(
            select(func.avg(func.extract("epoch", AdminTask.handled_at - AdminTask.detected_at)))
            .where(AdminTask.status == TaskStatus.HANDLED, AdminTask.handled_at >= start)
        )
        return round(float(seconds) / 60) if seconds is not None else 0

    def last_scan_at(self) -> datetime | None:
        return self._db.scalar(
            select(func.max(AuditLog.created_at)).where(AuditLog.action == "anomaly_scan")
        )

    def existing_keys(self, keys: list[str]) -> set[str]:
        if not keys:
            return set()
        rows = self._db.scalars(
            select(AdminTask.dedupe_key).where(AdminTask.dedupe_key.in_(keys))
        ).all()
        return {str(key) for key in rows}

    # ------------------------------------------------------------------ 写入
    def reopen_expired(self, now: datetime) -> int:
        """稍后处理到期的任务重新打开；条件已消失的会在同一轮 resolve 中收敛。"""
        result = self._db.execute(
            update(AdminTask)
            .where(
                AdminTask.status == TaskStatus.SNOOZED,
                AdminTask.snoozed_until.is_not(None),
                AdminTask.snoozed_until <= now,
            )
            .values(status=TaskStatus.OPEN, snoozed_until=None, updated_at=now)
        )
        return result.rowcount or 0

    def upsert(self, rows: list[dict], now: datetime) -> int:
        if not rows:
            return 0
        stmt = pg_insert(AdminTask).values(rows)
        finished = ~AdminTask.status.in_((TaskStatus.OPEN, TaskStatus.SNOOZED))
        stmt = stmt.on_conflict_do_update(
            index_elements=[AdminTask.dedupe_key],
            set_={
                "severity": stmt.excluded.severity,
                "title": stmt.excluded.title,
                "detail": stmt.excluded.detail,
                "updated_at": now,
                # 已人工处理/忽略的任务不被扫描改写等待时长
                "detected_at": case(
                    (finished, AdminTask.detected_at), else_=stmt.excluded.detected_at
                ),
                # 自动收敛过的任务如果条件重新成立，重新打开
                "status": case(
                    (AdminTask.status == TaskStatus.RESOLVED, TaskStatus.OPEN),
                    else_=AdminTask.status,
                ),
            },
        )
        self._db.execute(stmt)
        return len(rows)

    def resolve_stale(self, keys: list[str], now: datetime) -> int:
        """本轮未命中的 open 任务置为 resolved；snoozed 由到期逻辑处理。"""
        stmt = update(AdminTask).where(AdminTask.status == TaskStatus.OPEN)
        if keys:
            stmt = stmt.where(AdminTask.dedupe_key.not_in(keys))
        result = self._db.execute(
            stmt.values(status=TaskStatus.RESOLVED, snoozed_until=null(), updated_at=now)
        )
        return result.rowcount or 0
