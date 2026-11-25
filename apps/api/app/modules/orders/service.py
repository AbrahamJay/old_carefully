"""订单领域服务。

所有订单相关的业务规则都在这里，HTTP 路由与（未来的）agent 工具共用同一套能力。
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from ...core.enums import (
    AssignmentStatus,
    NotificationType,
    OrderStatus,
    PaymentStatus,
    Role,
    UserStatus,
)
from ...core.errors import BadRequestError, ConflictError, ForbiddenError, NotFoundError
from ...core.ids import new_order_no
from ...core.time import utcnow
from ...db.models import Order, OrderAssignment, Review, ServiceRecord, User
from ...domain.authz import (
    can_access_loaded_order,
    get_staff_assignment,
    order_query_for_user,
)
from ...domain.order_flow import ensure_cancellable, ensure_transition
from ...domain.pricing import calc_deposit
from ..audit import AuditService
from ..catalog import CatalogService
from ..elders import ElderService
from ..notifications import NotificationService
from ..payments import PaymentService, PaymentTotals
from .repository import OrderRepository
from .schemas import OrderCreate, RecordCreate, ReviewCreate


class OrderService:
    def __init__(
        self,
        db: Session,
        repo: OrderRepository,
        payments: PaymentService,
        notifier: NotificationService,
        audit: AuditService,
        elders: ElderService,
        catalog: CatalogService,
    ) -> None:
        self._db = db
        self._repo = repo
        self._payments = payments
        self._notifier = notifier
        self._audit = audit
        self._elders = elders
        self._catalog = catalog

    # ------------------------------------------------------------------ 查询
    def totals_of(self, order: Order) -> PaymentTotals:
        return self._payments.totals(order)

    def get_for_actor(self, actor: User, order_id: int) -> Order:
        order = self._repo.get(order_id)
        if order is None:
            raise NotFoundError("订单不存在")
        if not can_access_loaded_order(actor, order):
            raise ForbiddenError()
        return order

    def list_page(
        self,
        actor: User,
        *,
        status: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[Order], int]:
        base = order_query_for_user(actor)
        if status:
            base = base.where(Order.status == status)
        total = self._repo.count(base)
        items = self._repo.page(base, offset=(page - 1) * page_size, limit=page_size)
        return items, total

    def admin_page(
        self,
        *,
        status: str | None,
        station_id: int | None,
        keyword: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[Order], int]:
        base = self._repo.admin_query(status=status, station_id=station_id, keyword=keyword)
        total = self._repo.count(base)
        items = self._repo.page(base, offset=(page - 1) * page_size, limit=page_size)
        return items, total

    # ------------------------------------------------------------------ 下单
    def create(self, actor: User, payload: OrderCreate) -> Order:
        if actor.role != Role.CUSTOMER:
            raise ForbiddenError("员工账号用于接单履约，不能下单；请使用家属账号预约")

        elder = self._elders.get_accessible(
            actor, payload.elder_id, forbidden_message="未绑定该老人"
        )
        service = self._catalog.get_bookable(payload.service_id)

        outstanding = self._payments.find_outstanding_order(actor.id)
        if outstanding is not None:
            raise ConflictError(f"订单 {outstanding.order_no} 还有未结清尾款，请先结清后再预约")

        amount_cents = service.price_cents
        order = Order(
            order_no=new_order_no(),
            station_id=elder.station_id,
            elder_id=elder.id,
            customer_id=actor.id,
            service_id=service.id,
            status=OrderStatus.PENDING_CONFIRM,
            scheduled_at=payload.scheduled_at,
            address=payload.address or elder.address,
            contact_name=payload.contact_name or elder.name,
            contact_phone=payload.contact_phone or elder.phone,
            notes=payload.notes,
            amount_cents=amount_cents,
            deposit_cents=calc_deposit(amount_cents),
            payment_status=PaymentStatus.UNPAID,
        )
        self._db.add(order)
        self._db.flush()
        self._notify(
            actor.id,
            NotificationType.ORDER_CREATED,
            "下单成功",
            f"{service.name} 已提交，等待管家确认。",
            order.id,
        )
        self._db.commit()
        return self._reload(order.id)

    # ------------------------------------------------------------------ 状态流转
    def cancel(self, actor: User, order_id: int) -> Order:
        order = self.get_for_actor(actor, order_id)
        ensure_cancellable(order.status)

        order.status = OrderStatus.CANCELLED
        order.cancel_reason = "用户取消" if actor.role == Role.CUSTOMER else "管理员取消"

        totals = self._payments.totals(order)
        if totals.net_cents > 0:
            self._payments.refund(order, actor, reason="cancel")

        # 释放仍在进行中的派单，避免员工侧残留"幽灵任务"
        for assignment in self._repo.active_assignments(order.id):
            assignment.status = AssignmentStatus.REJECTED

        self._notify(
            order.customer_id,
            NotificationType.ORDER_CANCELLED,
            "订单已取消",
            f"订单 {order.order_no} 已取消。",
            order.id,
        )
        self._audit.record(actor.id, "cancel", "order", order.id)
        self._db.commit()
        return self._reload(order.id)

    def confirm(self, actor: User, order_id: int) -> Order:
        order = self.get_for_actor(actor, order_id)
        ensure_transition(order.status, OrderStatus.CONFIRMED)
        order.status = OrderStatus.CONFIRMED
        self._notify(
            order.customer_id,
            NotificationType.ORDER_CONFIRMED,
            "订单已确认",
            f"订单 {order.order_no} 已确认。",
            order.id,
        )
        self._audit.record(actor.id, "confirm", "order", order.id)
        self._db.commit()
        return self._reload(order.id)

    def assign(self, actor: User, order_id: int, staff_id: int) -> Order:
        order = self.get_for_actor(actor, order_id)
        if order.status not in (OrderStatus.CONFIRMED, OrderStatus.ASSIGNED):
            raise ConflictError("当前状态不能派单")

        staff = self._repo.get_staff(staff_id)
        if staff is None or staff.role != Role.STAFF or staff.status != UserStatus.ACTIVE:
            raise BadRequestError("员工不存在或不可用")
        if order.station_id and staff.station_id != order.station_id:
            raise BadRequestError("该员工不属于本订单区域，请选择同区域员工")

        for previous in self._repo.active_assignments(order.id):
            previous.status = AssignmentStatus.REJECTED

        self._db.add(
            OrderAssignment(order_id=order.id, staff_id=staff.id, status=AssignmentStatus.ASSIGNED)
        )
        order.status = OrderStatus.ASSIGNED
        self._notify(
            staff.id,
            NotificationType.ORDER_ASSIGNED,
            "新派单",
            f"订单 {order.order_no} 已派给你。",
            order.id,
        )
        self._notify(
            order.customer_id,
            NotificationType.ORDER_ASSIGNED,
            "已安排服务人员",
            f"{staff.name} 将为您服务。",
            order.id,
        )
        self._audit.record(actor.id, "assign", "order", order.id, {"staff_id": staff.id})
        self._db.commit()
        return self._reload(order.id)

    def accept(self, actor: User, order_id: int) -> Order:
        order = self.get_for_actor(actor, order_id)
        assignment = self._require_assignment(order, actor)
        if order.status != OrderStatus.ASSIGNED or assignment.status not in (
            AssignmentStatus.ASSIGNED,
            AssignmentStatus.ACCEPTED,
        ):
            raise ConflictError("当前状态不能接单")

        assignment.status = AssignmentStatus.ACCEPTED
        assignment.accepted_at = utcnow()
        self._notify(
            order.customer_id,
            NotificationType.ORDER_ASSIGNED,
            "服务人员已接单",
            f"{actor.name} 已接单。",
            order.id,
        )
        self._db.commit()
        return self._reload(order.id)

    def start(self, actor: User, order_id: int) -> Order:
        order = self.get_for_actor(actor, order_id)
        self._require_assignment(order, actor, accepted_only=True)
        if order.status != OrderStatus.ASSIGNED:
            raise ConflictError("当前状态不能开始服务")

        totals = self._payments.totals(order)
        if order.deposit_cents > 0 and totals.net_cents < order.deposit_cents:
            raise ConflictError("请先支付定金后再开始服务")

        order.status = OrderStatus.IN_SERVICE
        self._notify(
            order.customer_id,
            NotificationType.ORDER_STARTED,
            "服务已开始",
            f"订单 {order.order_no} 已开始服务。",
            order.id,
        )
        self._audit.record(actor.id, "start", "order", order.id)
        self._db.commit()
        return self._reload(order.id)

    def complete(self, actor: User, order_id: int) -> Order:
        order = self.get_for_actor(actor, order_id)
        assignment = self._require_assignment(order, actor, accepted_only=True)
        if order.status != OrderStatus.IN_SERVICE:
            raise ConflictError("当前状态不能完成")
        if not self._repo.has_record(order.id):
            raise ConflictError("请先提交服务记录")

        order.status = OrderStatus.COMPLETED
        assignment.status = AssignmentStatus.COMPLETED
        assignment.completed_at = utcnow()
        self._notify(
            order.customer_id,
            NotificationType.ORDER_COMPLETED,
            "服务已完成",
            f"订单 {order.order_no} 已完成，可以查看服务记录并评价。",
            order.id,
        )
        self._audit.record(actor.id, "complete", "order", order.id)
        self._db.commit()
        return self._reload(order.id)

    # ------------------------------------------------------------------ 资金
    def pay(self, actor: User, order_id: int) -> Order:
        order = self.get_for_actor(actor, order_id)
        _, plan = self._payments.pay_online(order, actor)
        self._notify(
            order.customer_id,
            NotificationType.ORDER_PAID,
            f"已支付{plan.kind}",
            f"订单 {order.order_no} 已支付{plan.kind} ¥{plan.amount_cents / 100:.2f}。",
            order.id,
        )
        self._audit.record(
            actor.id,
            "pay_and_confirm" if plan.kind == "尾款" else "pay",
            "order",
            order.id,
            {"amount_cents": plan.amount_cents, "kind": plan.kind},
        )
        self._db.commit()
        return self._reload(order.id)

    def pay_offline(self, actor: User, order_id: int, *, method: str) -> Order:
        order = self.get_for_actor(actor, order_id)
        _, plan = self._payments.pay_offline(order, actor, method=method)
        self._notify(
            order.customer_id,
            NotificationType.ORDER_PAID,
            f"已收{plan.kind}",
            f"订单 {order.order_no} 已确认线下收款 {plan.kind} ¥{plan.amount_cents / 100:.2f}。",
            order.id,
        )
        self._audit.record(
            actor.id,
            "mark_paid",
            "order",
            order.id,
            {"amount_cents": plan.amount_cents, "kind": plan.kind},
        )
        self._db.commit()
        return self._reload(order.id)

    def refund(self, actor: User, order_id: int) -> Order:
        order = self.get_for_actor(actor, order_id)
        payment = self._payments.refund(order, actor, reason="admin_refund")
        self._notify(
            order.customer_id,
            NotificationType.ORDER_REFUNDED,
            "订单已退款",
            f"订单 {order.order_no} 已退款 ¥{payment.amount_cents / 100:.2f}。",
            order.id,
        )
        self._audit.record(
            actor.id, "refund", "order", order.id, {"amount_cents": payment.amount_cents}
        )
        self._db.commit()
        return self._reload(order.id)

    # ------------------------------------------------------------------ 服务记录
    def add_record(self, actor: User, order_id: int, payload: RecordCreate) -> ServiceRecord:
        order = self.get_for_actor(actor, order_id)
        self._require_assignment(order, actor, accepted_only=True)
        if order.status != OrderStatus.IN_SERVICE:
            raise ConflictError("服务开始后才能提交记录")

        content = payload.content.strip()
        if not content and not payload.photos:
            raise BadRequestError("请填写服务记录或上传至少一张照片")

        record = ServiceRecord(
            order_id=order.id,
            staff_id=actor.id,
            checkin_at=payload.checkin_at or utcnow(),
            content=content or "已上传服务照片",
            photos=payload.photos,
            # 员工只能提交记录，不能替长辈/家属确认
            elder_confirmed=False,
        )
        self._db.add(record)
        self._db.commit()
        self._db.refresh(record)
        return record

    def list_records(self, actor: User, order_id: int) -> list[ServiceRecord]:
        order = self.get_for_actor(actor, order_id)
        return self._repo.list_records(order.id)

    def confirm_service(self, actor: User, order_id: int) -> Order:
        order = self.get_for_actor(actor, order_id)
        if order.status != OrderStatus.COMPLETED:
            raise ConflictError("服务完成后才能确认")
        record = self._repo.latest_record(order.id)
        if record is None:
            raise ConflictError("还没有服务记录")
        record.elder_confirmed = True
        self._audit.record(actor.id, "confirm_service", "order", order.id)
        self._db.commit()
        return self._reload(order.id)

    # ------------------------------------------------------------------ 评价
    def review(self, actor: User, order_id: int, payload: ReviewCreate) -> Review:
        order = self.get_for_actor(actor, order_id)
        if order.customer_id != actor.id:
            raise ForbiddenError()
        if order.status != OrderStatus.COMPLETED:
            raise ConflictError("服务完成后才能评价")
        if self._repo.get_review(order.id) is not None:
            raise BadRequestError("已经评价过了")

        review = Review(
            order_id=order.id,
            customer_id=actor.id,
            rating=payload.rating,
            content=payload.content,
        )
        self._db.add(review)
        self._db.commit()
        self._db.refresh(review)
        return review

    # ------------------------------------------------------------------ 内部
    def _require_assignment(
        self, order: Order, actor: User, *, accepted_only: bool = False
    ) -> OrderAssignment:
        assignment = get_staff_assignment(self._db, order.id, actor.id)
        if assignment is None:
            raise ForbiddenError("不是你的派单")
        if accepted_only and assignment.status != AssignmentStatus.ACCEPTED:
            raise ForbiddenError("请先接单")
        return assignment

    def _notify(
        self,
        user_id: int,
        ntype: str,
        title: str,
        body: str,
        order_id: int,
    ) -> None:
        self._notifier.notify(user_id, ntype, title, body, {"order_id": order_id})

    def _reload(self, order_id: int) -> Order:
        order = self._repo.reload(order_id)
        if order is None:
            raise NotFoundError("订单不存在")
        return order
