"""订单出参组装。

把 ORM 对象 + 聚合结果翻译为对外 DTO，保证 router 里不再出现拼装逻辑。
"""

from __future__ import annotations

from ...core.enums import AssignmentStatus, OrderStatus
from ...db.models import Order, OrderAssignment, ServiceRecord
from ..auth.schemas import UserOut
from ..catalog.schemas import ServiceOut
from ..elders.schemas import ElderOut
from ..payments import PaymentTotals
from .schemas import OrderDetailOut, OrderListItem, RecordOut, ReviewOut


def _display_assignment(order: Order) -> OrderAssignment | None:
    for assignment in reversed(order.assignments):
        if assignment.status in (
            AssignmentStatus.ASSIGNED,
            AssignmentStatus.ACCEPTED,
            AssignmentStatus.COMPLETED,
        ):
            return assignment
    return None


def _service_confirmed(order: Order) -> bool:
    return bool(order.records and order.records[-1].elder_confirmed)


def to_record(record: ServiceRecord) -> RecordOut:
    return RecordOut.model_validate(record)


def to_list_item(order: Order, totals: PaymentTotals) -> OrderListItem:
    assignment = _display_assignment(order)
    staff = assignment.staff if assignment else None
    return OrderListItem(
        id=order.id,
        order_no=order.order_no,
        status=order.status,
        payment_status=order.payment_status,
        service_name=order.service.name if order.service else "",
        elder_name=order.elder.name if order.elder else "",
        staff_name=staff.name if staff else "",
        station_id=order.station_id,
        station_name=order.station.name if order.station else "",
        deposit_cents=order.deposit_cents,
        paid_cents=totals.paid_cents,
        remaining_cents=totals.remaining_cents,
        service_confirmed=_service_confirmed(order),
        scheduled_at=order.scheduled_at,
        amount_cents=order.amount_cents,
        created_at=order.created_at,
    )


def to_detail(order: Order, totals: PaymentTotals) -> OrderDetailOut:
    assignment = order.assignments[-1] if order.assignments else None
    staff = assignment.staff if assignment else None
    paid, refunded, _, remaining = (
        totals.paid_cents,
        totals.refunded_cents,
        totals.net_cents,
        totals.remaining_cents,
    )
    return OrderDetailOut(
        id=order.id,
        order_no=order.order_no,
        status=order.status,
        payment_status=order.payment_status,
        scheduled_at=order.scheduled_at,
        address=order.address,
        contact_name=order.contact_name,
        contact_phone=order.contact_phone,
        notes=order.notes,
        amount_cents=order.amount_cents,
        deposit_cents=order.deposit_cents,
        paid_cents=paid,
        refunded_cents=refunded,
        remaining_cents=remaining,
        service_confirmed=_service_confirmed(order),
        cancel_reason=order.cancel_reason,
        created_at=order.created_at,
        updated_at=order.updated_at,
        station_id=order.station_id,
        station_name=order.station.name if order.station else "",
        elder=ElderOut.model_validate(order.elder),
        service=ServiceOut.model_validate(order.service),
        staff=UserOut.model_validate(staff) if staff else None,
        records=[to_record(record) for record in order.records],
        review=ReviewOut.model_validate(order.review) if order.review else None,
    )


def is_completed(order: Order) -> bool:
    return order.status == OrderStatus.COMPLETED
