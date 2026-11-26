"""订单领域服务。

所有订单相关的业务规则都在这里，HTTP 路由与（未来的）agent 工具共用同一套能力。
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ...core.config import settings
from ...core.enums import (
    AssignmentStatus,
    NotificationType,
    OrderStatus,
    PaymentStatus,
    Role,
    StaffStatus,
    UserStatus,
)
from ...core.errors import (
    BadRequestError,
    ConflictError,
    FeatureUnavailableError,
    ForbiddenError,
    NotFoundError,
)
from ...core.ids import new_order_no
from ...core.time import business_day_start_utc, business_tz, utcnow
from ...db.models import Order, OrderAssignment, Review, ServiceRecord, StaffProfile, User
from ...domain.authz import (
    can_access_loaded_order,
    get_staff_assignment,
    order_query_for_user,
)
from ...domain.order_flow import CANCELLABLE, ensure_cancellable, ensure_transition
from ...domain.order_time import intervals_overlap, order_interval
from ...domain.pricing import calc_deposit
from ..audit import AuditService
from ..catalog import CatalogService
from ..elders import ElderService
from ..notifications import NotificationService
from ..payments import PaymentService, PaymentTotals
from .candidates import (
    CandidateReport,
    OrderContext,
    StaffSnapshot,
    TimeSlot,
    evaluate,
)
from .repository import OrderRepository
from .schemas import DispatchSummaryOut, OrderCreate, RecordCreate, ReviewCreate

logger = logging.getLogger(__name__)


def _format_slot(start: datetime, end: datetime) -> str:
    """冲突提示用：按业务时区展示时段。"""
    tz = business_tz()
    return (
        f"{start.astimezone(tz).strftime('%m-%d %H:%M')} - "
        f"{end.astimezone(tz).strftime('%m-%d %H:%M')}"
    )


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

    # ------------------------------------------------------------------ 候选
    def list_candidates(self, actor: User, order_id: int) -> CandidateReport:
        """规则候选：硬过滤 + 100 分排序，不写库、不调用 LLM。"""
        if not settings.candidate_ranking_enabled:
            # 灰度开关：前端据此隐藏建议卡，回退到手工派单
            raise FeatureUnavailableError("候选排序未启用", http_status=503)
        order = self.get_for_actor(actor, order_id)
        ctx = self._order_context(order)

        rows = self._repo.candidate_staff()
        same_station_ids = [
            user.id
            for user, _ in rows
            if ctx.station_id is not None and user.station_id == ctx.station_id
        ]
        leaves = self._repo.staff_on_leave(same_station_ids, ctx.business_date)
        loads = self._repo.staff_day_loads(
            same_station_ids,
            day_start=business_day_start_utc(today=ctx.business_date),
            day_end=business_day_start_utc(1, today=ctx.business_date),
            exclude_order_id=order.id,
        )
        busy = self._repo.staff_busy_slots(
            same_station_ids,
            # 前后各多取一天，覆盖跨午夜订单
            window_start=business_day_start_utc(-1, today=ctx.business_date),
            window_end=business_day_start_utc(2, today=ctx.business_date),
            exclude_order_id=order.id,
        )
        snapshots = tuple(
            self._staff_snapshot(user, profile, leaves, loads, busy)
            for user, profile in rows
        )
        evaluation = evaluate(ctx, snapshots)
        return CandidateReport(
            order_id=order.id,
            generated_at=utcnow(),
            required_skill=ctx.required_skill,
            candidates=evaluation.candidates,
            excluded=evaluation.excluded,
            data_gaps=evaluation.data_gaps,
        )

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
        self._mark_status_changed(order)

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
        self._ensure_not_refunded(order, "确认")
        ensure_transition(order.status, OrderStatus.CONFIRMED)
        order.status = OrderStatus.CONFIRMED
        self._mark_status_changed(order)
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
        self._ensure_not_refunded(order, "派单")

        staff = self._repo.get_staff(staff_id)
        if staff is None or staff.role != Role.STAFF or staff.status != UserStatus.ACTIVE:
            raise BadRequestError("员工不存在或不可用")
        if order.station_id and staff.station_id != order.station_id:
            raise BadRequestError("该员工不属于本订单区域，请选择同区域员工")

        self._ensure_staff_free(order, staff)

        for previous in self._repo.active_assignments(order.id):
            previous.status = AssignmentStatus.REJECTED

        self._db.add(
            OrderAssignment(order_id=order.id, staff_id=staff.id, status=AssignmentStatus.ASSIGNED)
        )
        order.status = OrderStatus.ASSIGNED
        self._mark_status_changed(order)
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

    def confirm_and_assign(
        self,
        actor: User,
        order_id: int,
        staff_id: int,
        expected_updated_at: datetime | None = None,
    ) -> Order:
        """确认 + 派单：行锁 + 单事务，任一步失败全部回滚。

        与先调 ``confirm`` 再调 ``assign`` 的区别：只刷一次状态时间、只写一条
        ``confirm_and_assign`` 审计，不会留下「已确认未派单」的中间态。
        """
        order = self._repo.get_for_update(order_id)
        if order is None:
            raise NotFoundError("订单不存在")
        if order.status not in (OrderStatus.PENDING_CONFIRM, OrderStatus.CONFIRMED):
            if order.status == OrderStatus.ASSIGNED:
                raise ConflictError("订单已派单，请刷新后重试")
            raise ConflictError("当前状态不能确认派单")
        self._ensure_not_refunded(order, "确认派单")

        # 乐观并发：可选参数，前端从详情带入 updated_at；两人同时处理时只放行一个
        if expected_updated_at is not None:
            expected = expected_updated_at
            if expected.tzinfo is None:
                expected = expected.replace(tzinfo=timezone.utc)
            if abs((order.updated_at - expected).total_seconds()) > 1e-6:
                raise ConflictError("订单已被其他人处理，请刷新后重试")

        staff = self._repo.get_staff(staff_id)
        if staff is None or staff.role != Role.STAFF or staff.status != UserStatus.ACTIVE:
            raise BadRequestError("员工不存在或不可用")
        if order.station_id and staff.station_id != order.station_id:
            raise BadRequestError("该员工不属于本订单区域，请选择同区域员工")

        self._ensure_staff_free(order, staff)

        original_status = order.status
        if original_status == OrderStatus.PENDING_CONFIRM:
            order.status = OrderStatus.CONFIRMED
        for previous in self._repo.active_assignments(order.id):
            previous.status = AssignmentStatus.REJECTED

        self._db.add(
            OrderAssignment(
                order_id=order.id,
                staff_id=staff.id,
                status=AssignmentStatus.ASSIGNED,
            )
        )
        order.status = OrderStatus.ASSIGNED
        self._mark_status_changed(order)
        self._audit.record(
            actor.id,
            "confirm_and_assign",
            "order",
            order.id,
            {"staff_id": staff.id, "from_status": original_status},
        )
        self._db.flush()

        # 通知写库失败不回滚业务：savepoint 只回滚通知，并记日志便于补发
        try:
            with self._db.begin_nested():
                self._notify(
                    order.customer_id,
                    NotificationType.ORDER_CONFIRMED,
                    "订单已确认",
                    f"订单 {order.order_no} 已确认。",
                    order.id,
                )
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
        except Exception:
            # 通知失败不能中断已完成的确认派单，记录日志便于补发
            logger.exception(
                "确认派单通知写入失败：order_id=%s staff_id=%s", order.id, staff.id
            )

        self._db.commit()
        return self._reload(order.id)

    def dispatch_summary(self) -> DispatchSummaryOut:
        """派单工作台顶部指标，按业务日统计。"""
        day_start = business_day_start_utc()
        return DispatchSummaryOut(
            pending_confirm=self._repo.count_by_status(OrderStatus.PENDING_CONFIRM),
            confirmed=self._repo.count_by_status(OrderStatus.CONFIRMED),
            dispatched_today=self._repo.count_dispatched_since(day_start),
            handled_today=self._repo.count_since(
                day_start,
                (OrderStatus.ASSIGNED, OrderStatus.IN_SERVICE, OrderStatus.COMPLETED),
            ),
        )

    def accept(self, actor: User, order_id: int) -> Order:
        order = self.get_for_actor(actor, order_id)
        self._ensure_not_refunded(order, "接单")
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
        self._ensure_not_refunded(order, "开始服务")
        self._require_assignment(order, actor, accepted_only=True)
        if order.status != OrderStatus.ASSIGNED:
            raise ConflictError("当前状态不能开始服务")

        totals = self._payments.totals(order)
        if order.deposit_cents > 0 and totals.net_cents < order.deposit_cents:
            raise ConflictError("请先支付定金后再开始服务")

        order.status = OrderStatus.IN_SERVICE
        self._mark_status_changed(order)
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
        self._mark_status_changed(order)
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
        # 退款即终止订单：只退钱不改状态会留下「已退款却还能派单」的单子
        cancelled = False
        if order.status in CANCELLABLE:
            order.status = OrderStatus.CANCELLED
            order.cancel_reason = "退款自动取消"
            self._mark_status_changed(order)
            for assignment in self._repo.active_assignments(order.id):
                assignment.status = AssignmentStatus.REJECTED
            cancelled = True
        self._notify(
            order.customer_id,
            NotificationType.ORDER_REFUNDED,
            "订单已退款",
            f"订单 {order.order_no} 已退款 ¥{payment.amount_cents / 100:.2f}。",
            order.id,
        )
        self._audit.record(
            actor.id,
            "refund",
            "order",
            order.id,
            {"amount_cents": payment.amount_cents, "cancelled": cancelled},
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
    def _order_context(self, order: Order) -> OrderContext:
        duration = order.service.duration_minutes if order.service else None
        start, end = order_interval(order.scheduled_at, duration)
        local_start = start.astimezone(business_tz())
        local_end = end.astimezone(business_tz())
        return OrderContext(
            order_id=order.id,
            station_id=order.station_id
            or (order.elder.station_id if order.elder else None),
            required_skill=order.service.required_skill if order.service else None,
            start=start,
            end=end,
            tz=business_tz(),
            business_date=local_start.date(),
            weekday=local_start.isoweekday(),
            start_minute=local_start.hour * 60 + local_start.minute,
            end_minute=local_end.hour * 60 + local_end.minute,
            same_day=local_end.date() == local_start.date(),
            elder_community=order.elder.community if order.elder else "",
        )

    def _staff_snapshot(
        self,
        user: User,
        profile: StaffProfile | None,
        leaves: set[int],
        loads: dict[int, int],
        busy: dict[int, list[Order]],
    ) -> StaffSnapshot:
        slots: list[TimeSlot] = []
        for other in busy.get(user.id, []):
            other_start, other_end = order_interval(
                other.scheduled_at,
                other.service.duration_minutes if other.service else None,
            )
            slots.append(TimeSlot(other_start, other_end, other.order_no))
        return StaffSnapshot(
            staff_id=user.id,
            name=user.name,
            station_id=user.station_id,
            station_name=user.station.name if user.station else "",
            station_address=user.station.address if user.station else "",
            skills=tuple(profile.skills if profile else ()),
            rating=profile.rating if profile else 5.0,
            user_active=user.status == UserStatus.ACTIVE,
            profile_active=(profile.status == StaffStatus.ACTIVE) if profile else True,
            profile_present=profile is not None,
            accepting_orders=profile.accepting_orders if profile else True,
            work_days=tuple(profile.work_days if profile else (1, 2, 3, 4, 5, 6, 7)),
            work_start_minute=profile.work_start_minute if profile else 480,
            work_end_minute=profile.work_end_minute if profile else 1080,
            daily_capacity=profile.daily_capacity if profile else 4,
            on_leave=user.id in leaves,
            load=loads.get(user.id, 0),
            busy=tuple(slots),
        )

    def _mark_status_changed(self, order: Order) -> None:
        """订单状态变化时刷新停留计时；改地址/备注等字段不调用本方法。"""
        order.status_changed_at = utcnow()

    def _ensure_staff_free(self, order: Order, staff: User) -> None:
        """派单前校验时段冲突（左闭右开，首尾相接不算冲突）。

        候选人结果可能已过期（别人刚派了单），所以不能只在列表过滤，
        落库前必须再验证一次；阶段三的组合派单也复用本方法。
        """
        duration = order.service.duration_minutes if order.service else None
        start, end = order_interval(order.scheduled_at, duration)
        # 前后各多取一天，覆盖跨午夜与超长时段的订单
        local_day = order.scheduled_at.astimezone(business_tz()).date()
        busy = self._repo.staff_busy_orders(
            staff.id,
            window_start=business_day_start_utc(-1, today=local_day),
            window_end=business_day_start_utc(2, today=local_day),
            exclude_order_id=order.id,
        )
        for other in busy:
            other_duration = other.service.duration_minutes if other.service else None
            other_start, other_end = order_interval(other.scheduled_at, other_duration)
            if intervals_overlap(start, end, other_start, other_end):
                raise ConflictError(
                    f"该员工在 {_format_slot(other_start, other_end)} 已有订单 "
                    f"{other.order_no}，请换人或调整预约时间"
                )

    def _ensure_not_refunded(self, order: Order, action: str) -> None:
        """已退款订单只作历史留档：派单/接单/开始服务一律拒绝，避免派出收不到钱的服务。"""
        if order.payment_status == PaymentStatus.REFUNDED:
            raise ConflictError(f"订单已退款，不能{action}")

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
