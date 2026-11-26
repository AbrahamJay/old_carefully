"""异常扫描规则。

只读订单事实，产出待写入 ``admin_tasks`` 的条目。判定口径与《Agent数据底座概要设计》
§5.6 一致：阈值全部来自 settings，SQL 负责粗筛，服务时长/跨午夜计算复用
``domain.order_time``。这里不调用 LLM，「为什么被标记」由规则事实拼出来。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ...core.config import settings
from ...core.enums import (
    AnomalyType,
    AssignmentStatus,
    OrderStatus,
    PaymentRecordStatus,
    PaymentStatus,
    TaskSeverity,
)
from ...core.time import business_tz
from ...db.models import Order, OrderAssignment
from ...domain.order_time import order_interval

# 扫描需要的关联：一次取全，避免逐单查询
_EAGER = (
    selectinload(Order.elder),
    selectinload(Order.service),
    selectinload(Order.station),
    selectinload(Order.assignments).selectinload(OrderAssignment.staff),
    selectinload(Order.payments),
)


@dataclass(frozen=True)
class DetectedTask:
    """一条待落库的异常任务。``detail`` 只放结构化事实与规则解释。"""

    type: str
    order_id: int
    severity: str
    dedupe_key: str
    title: str
    detail: dict


def _minutes(start: datetime, now: datetime) -> int:
    return max(0, int((now - start).total_seconds() // 60))


def _fmt(value: datetime) -> str:
    return value.astimezone(business_tz()).strftime("%Y-%m-%d %H:%M")


def _key(task_type: str, order: Order) -> str:
    """同一订单同一状态只保留一条；状态时间变化会自然换新键。"""
    stamp = order.status_changed_at.isoformat() if order.status_changed_at else ""
    return f"{task_type}:{order.id}:{stamp}"


def _active_staff(order: Order) -> str:
    for assignment in order.assignments:
        if assignment.status in (AssignmentStatus.ASSIGNED, AssignmentStatus.ACCEPTED):
            return assignment.staff.name if assignment.staff else ""
    return ""


def _facts(order: Order, *, remaining_cents: int | None = None) -> dict:
    return {
        "order_no": order.order_no,
        "order_status": order.status,
        "elder_name": order.elder.name if order.elder else "",
        "community": order.elder.community if order.elder else "",
        "service_name": order.service.name if order.service else "",
        "scheduled_at": order.scheduled_at.isoformat(),
        "address": order.address,
        "station_name": order.station.name if order.station else "",
        "staff_name": _active_staff(order),
        "payment_status": order.payment_status,
        "remaining_cents": remaining_cents,
    }


def _detail(
    order: Order,
    *,
    rule: str,
    why: str,
    suggest: str,
    elapsed_minutes: int,
    threshold_minutes: int,
    remaining_cents: int | None = None,
) -> dict:
    return {
        "rule": rule,
        "why": why,
        "suggest": suggest,
        "elapsed_minutes": elapsed_minutes,
        "threshold_minutes": threshold_minutes,
        "facts": _facts(order, remaining_cents=remaining_cents),
    }


def _pending_timeout(db: Session, now: datetime) -> list[DetectedTask]:
    threshold = settings.anomaly_pending_confirm_minutes
    cutoff = now - timedelta(minutes=threshold)
    orders = db.scalars(
        select(Order)
        .options(*_EAGER)
        .where(
            Order.status == OrderStatus.PENDING_CONFIRM,
            Order.status_changed_at <= cutoff,
            # 已退款订单只留历史，不再催确认（历史数据可能还停在待确认）
            Order.payment_status != PaymentStatus.REFUNDED,
        )
    ).all()
    items: list[DetectedTask] = []
    for order in orders:
        elapsed = _minutes(order.status_changed_at, now)
        items.append(
            DetectedTask(
                type=AnomalyType.PENDING_TIMEOUT,
                order_id=order.id,
                severity=TaskSeverity.HIGH,
                dedupe_key=_key(AnomalyType.PENDING_TIMEOUT, order),
                title=f"待确认超时 · {order.order_no}",
                detail=_detail(
                    order,
                    rule=(
                        f"status = pending_confirm 且 payment_status <> refunded "
                        f"且 status_changed_at 早于 now - {threshold} 分钟"
                    ),
                    why=(
                        f"订单于 {_fmt(order.status_changed_at)} 进入待确认，"
                        f"已等待 {elapsed} 分钟，超过 {threshold} 分钟阈值。"
                    ),
                    suggest="先联系家属核对预约时间、地址和联系人；确认后到派单工作台选择服务人员。",
                    elapsed_minutes=elapsed,
                    threshold_minutes=threshold,
                ),
            )
        )
    return items


def _confirmed_unassigned(db: Session, now: datetime) -> list[DetectedTask]:
    threshold = settings.anomaly_confirmed_unassigned_minutes
    cutoff = now - timedelta(minutes=threshold)
    orders = db.scalars(
        select(Order)
        .options(*_EAGER)
        .where(
            Order.status == OrderStatus.CONFIRMED,
            Order.status_changed_at <= cutoff,
            # 已退款订单不再报「未派单」，避免和退款后的取消动作抢跑
            Order.payment_status != PaymentStatus.REFUNDED,
        )
    ).all()
    items: list[DetectedTask] = []
    for order in orders:
        elapsed = _minutes(order.status_changed_at, now)
        items.append(
            DetectedTask(
                type=AnomalyType.CONFIRMED_UNASSIGNED,
                order_id=order.id,
                severity=TaskSeverity.HIGH,
                dedupe_key=_key(AnomalyType.CONFIRMED_UNASSIGNED, order),
                title=f"已确认未派单 · {order.order_no}",
                detail=_detail(
                    order,
                    rule=(
                        f"status = confirmed 且 payment_status <> refunded "
                        f"且 status_changed_at 早于 now - {threshold} 分钟"
                    ),
                    why=(
                        f"订单于 {_fmt(order.status_changed_at)} 确认，"
                        f"已 {elapsed} 分钟仍未派单，超过 {threshold} 分钟阈值。"
                    ),
                    suggest=(
                        "到派单工作台查看候选员工；没有可用候选时联系家属改约，"
                        "或协调其他站点支援后手工派单。"
                    ),
                    elapsed_minutes=elapsed,
                    threshold_minutes=threshold,
                ),
            )
        )
    return items


def _assigned_not_accepted(db: Session, now: datetime) -> list[DetectedTask]:
    threshold = settings.anomaly_assigned_not_accepted_minutes
    cutoff = now - timedelta(minutes=threshold)
    rows = db.execute(
        select(Order, OrderAssignment)
        .join(OrderAssignment, OrderAssignment.order_id == Order.id)
        .options(*_EAGER)
        .where(
            Order.status == OrderStatus.ASSIGNED,
            OrderAssignment.status == AssignmentStatus.ASSIGNED,
            OrderAssignment.accepted_at.is_(None),
            OrderAssignment.assigned_at <= cutoff,
        )
        .order_by(OrderAssignment.assigned_at)
    ).all()
    items: list[DetectedTask] = []
    for order, assignment in rows:
        elapsed = _minutes(assignment.assigned_at, now)
        staff_name = assignment.staff.name if assignment.staff else ""
        detail = _detail(
            order,
            rule=(
                "status = assigned 且派单未接受（accepted_at 为空）"
                f"且 assigned_at 早于 now - {threshold} 分钟"
            ),
            why=(
                f"订单于 {_fmt(assignment.assigned_at)} 派给 {staff_name or '服务人员'}，"
                f"已 {elapsed} 分钟未接单，超过 {threshold} 分钟阈值。"
            ),
            suggest="联系员工确认是否接单；员工无法服务就改派同区域其他员工，或与家属改约。",
            elapsed_minutes=elapsed,
            threshold_minutes=threshold,
        )
        detail["facts"]["staff_name"] = staff_name
        items.append(
            DetectedTask(
                type=AnomalyType.ASSIGNED_NOT_ACCEPTED,
                order_id=order.id,
                severity=TaskSeverity.MEDIUM,
                dedupe_key=_key(AnomalyType.ASSIGNED_NOT_ACCEPTED, order),
                title=f"已派未接 · {order.order_no}",
                detail=detail,
            )
        )
    return items


def _in_service_overrun(db: Session, now: datetime) -> list[DetectedTask]:
    threshold = settings.anomaly_in_service_overrun_minutes
    orders = db.scalars(
        select(Order).options(*_EAGER).where(Order.status == OrderStatus.IN_SERVICE)
    ).all()
    items: list[DetectedTask] = []
    for order in orders:
        duration = order.service.duration_minutes if order.service else 60
        _, expected_end = order_interval(order.scheduled_at, duration)
        if now <= expected_end + timedelta(minutes=threshold):
            continue
        overrun = _minutes(expected_end, now)
        items.append(
            DetectedTask(
                type=AnomalyType.IN_SERVICE_OVERRUN,
                order_id=order.id,
                severity=TaskSeverity.MEDIUM,
                dedupe_key=_key(AnomalyType.IN_SERVICE_OVERRUN, order),
                title=f"服务中超时 · {order.order_no}",
                detail=_detail(
                    order,
                    rule=(
                        "status = in_service 且 now 超过「预约时间 + 服务时长"
                        f" + {threshold} 分钟」"
                    ),
                    why=(
                        f"服务预计 {_fmt(expected_end)} 结束，已超时 {overrun} 分钟，"
                        f"超过 {threshold} 分钟容差。"
                    ),
                    suggest="联系员工确认服务是否结束；结束后补服务记录并在小程序完成订单，避免尾款和评价卡住。",
                    elapsed_minutes=overrun,
                    threshold_minutes=threshold,
                ),
            )
        )
    return items


def _balance_due(db: Session, now: datetime) -> list[DetectedTask]:
    hours = settings.anomaly_balance_due_hours
    cutoff = now - timedelta(hours=hours)
    orders = db.scalars(
        select(Order)
        .options(*_EAGER)
        .where(Order.status == OrderStatus.COMPLETED, Order.status_changed_at <= cutoff)
    ).all()
    items: list[DetectedTask] = []
    for order in orders:
        paid = sum(
            item.amount_cents for item in order.payments if item.status == PaymentRecordStatus.PAID
        )
        refunded = sum(
            item.amount_cents
            for item in order.payments
            if item.status == PaymentRecordStatus.REFUNDED
        )
        remaining = max(order.amount_cents - max(paid - refunded, 0), 0)
        if remaining <= 0:
            continue
        elapsed = _minutes(order.status_changed_at, now)
        items.append(
            DetectedTask(
                type=AnomalyType.BALANCE_DUE,
                order_id=order.id,
                severity=TaskSeverity.LOW,
                dedupe_key=_key(AnomalyType.BALANCE_DUE, order),
                title=f"尾款未结 · {order.order_no}",
                detail=_detail(
                    order,
                    rule=(
                        "status = completed 且 remaining_cents > 0"
                        f"且 status_changed_at 早于 now - {hours} 小时"
                    ),
                    why=(
                        f"订单已完成 {elapsed // 60} 小时，仍有 ¥{remaining / 100:.2f} 未结清，"
                        f"超过 {hours} 小时阈值。"
                    ),
                    suggest="在服务订单里核对收款方式；线下收款后标记尾款，不要在这里直接改价或退款。",
                    elapsed_minutes=elapsed,
                    threshold_minutes=hours * 60,
                    remaining_cents=remaining,
                ),
            )
        )
    return items


def _missing_record(db: Session, now: datetime) -> list[DetectedTask]:
    orders = db.scalars(
        select(Order)
        .options(*_EAGER)
        .where(Order.status == OrderStatus.COMPLETED, ~Order.records.any())
    ).all()
    items: list[DetectedTask] = []
    for order in orders:
        elapsed = _minutes(order.status_changed_at, now)
        items.append(
            DetectedTask(
                type=AnomalyType.MISSING_RECORD,
                order_id=order.id,
                severity=TaskSeverity.LOW,
                dedupe_key=_key(AnomalyType.MISSING_RECORD, order),
                title=f"缺服务记录 · {order.order_no}",
                detail=_detail(
                    order,
                    rule="status = completed 且不存在任何服务记录（立即命中）",
                    why=f"订单于 {_fmt(order.status_changed_at)} 完成，但没有员工服务记录。",
                    suggest="联系服务人员补交记录与照片；补交后到订单详情确认服务，避免后续回访无依据。",
                    elapsed_minutes=elapsed,
                    threshold_minutes=0,
                ),
            )
        )
    return items


def detect(db: Session, now: datetime) -> list[DetectedTask]:
    """跑一遍全部规则，返回当前应存在的任务集合。"""
    items: list[DetectedTask] = []
    items.extend(_pending_timeout(db, now))
    items.extend(_confirmed_unassigned(db, now))
    items.extend(_assigned_not_accepted(db, now))
    items.extend(_in_service_overrun(db, now))
    items.extend(_balance_due(db, now))
    items.extend(_missing_record(db, now))
    return items
