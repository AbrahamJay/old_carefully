from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session, selectinload

from ...core.enums import AssignmentStatus, OrderStatus, Role
from ...db.models import (
    Elder,
    Order,
    OrderAssignment,
    Review,
    ServiceRecord,
    StaffLeave,
    StaffProfile,
    User,
)

# 列表/详情共用的预加载：一次性把展示所需的关联取回，避免 N+1
_EAGER = (
    selectinload(Order.elder).selectinload(Elder.station),
    selectinload(Order.service),
    selectinload(Order.station),
    selectinload(Order.assignments).selectinload(OrderAssignment.staff),
    selectinload(Order.payments),
    selectinload(Order.records),
    selectinload(Order.review),
)


class OrderRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def get(self, order_id: int) -> Order | None:
        return self._db.scalars(select(Order).where(Order.id == order_id).options(*_EAGER)).first()

    def get_for_update(self, order_id: int) -> Order | None:
        """行锁读取：组合式确认派单用，避免并发请求各自校验后都写入。"""
        stmt = (
            select(Order)
            .where(Order.id == order_id)
            .options(*_EAGER)
            .with_for_update()
        )
        return self._db.scalars(stmt).first()

    def reload(self, order_id: int) -> Order | None:
        """强制重新读取（含关联集合），用于写操作后的回显。

        ``expire_on_commit=False`` 会让 identity map 保留旧对象，
        必须加 ``populate_existing`` 才能拿到刚写入的 payments / records。
        """
        stmt = (
            select(Order)
            .where(Order.id == order_id)
            .options(*_EAGER)
            .execution_options(populate_existing=True)
        )
        return self._db.scalars(stmt).first()

    def count(self, base_stmt: Select) -> int:
        return self._db.scalar(select(func.count()).select_from(base_stmt.subquery())) or 0

    def page(self, base_stmt: Select, *, offset: int, limit: int) -> list[Order]:
        stmt = base_stmt.options(*_EAGER).order_by(Order.id.desc()).offset(offset).limit(limit)
        return list(self._db.scalars(stmt).unique().all())

    def admin_query(
        self,
        *,
        status: str | None,
        station_id: int | None,
        keyword: str | None,
    ) -> Select:
        stmt = select(Order)
        if status:
            stmt = stmt.where(Order.status == status)
        if station_id:
            stmt = stmt.where(Order.station_id == station_id)
        if keyword:
            # 用 ilike：编译为 PG 的 ILIKE（大小写不敏感）
            pattern = f"%{keyword.strip()}%"
            stmt = stmt.join(Elder, Elder.id == Order.elder_id).where(
                or_(
                    Order.order_no.ilike(pattern),
                    Elder.name.ilike(pattern),
                    Order.contact_name.ilike(pattern),
                    Order.contact_phone.ilike(pattern),
                )
            )
        return stmt

    # ---------------------------------------------------------------- 关联查询
    def latest_record(self, order_id: int) -> ServiceRecord | None:
        return self._db.scalars(
            select(ServiceRecord)
            .where(ServiceRecord.order_id == order_id)
            .order_by(ServiceRecord.id.desc())
        ).first()

    def has_record(self, order_id: int) -> bool:
        return (
            self._db.scalars(
                select(ServiceRecord.id).where(ServiceRecord.order_id == order_id).limit(1)
            ).first()
            is not None
        )

    def list_records(self, order_id: int) -> list[ServiceRecord]:
        return list(
            self._db.scalars(
                select(ServiceRecord)
                .where(ServiceRecord.order_id == order_id)
                .order_by(ServiceRecord.id)
            ).all()
        )

    def get_review(self, order_id: int) -> Review | None:
        return self._db.scalars(select(Review).where(Review.order_id == order_id)).first()

    def get_staff(self, staff_id: int) -> User | None:
        return self._db.get(User, staff_id)

    def active_assignments(self, order_id: int) -> list[OrderAssignment]:
        return list(
            self._db.scalars(
                select(OrderAssignment).where(
                    OrderAssignment.order_id == order_id,
                    OrderAssignment.status.in_(
                        (AssignmentStatus.ASSIGNED, AssignmentStatus.ACCEPTED)
                    ),
                )
            ).all()
        )

    def staff_busy_orders(
        self,
        staff_id: int,
        *,
        window_start: datetime,
        window_end: datetime,
        exclude_order_id: int | None = None,
    ) -> list[Order]:
        """员工在时间窗内已占用时段的订单（已派/已接/服务中）。

        精确的重叠判定交给 ``domain.order_time``：这里只按预约时间粗筛，
        避免把时长计算写进 SQL（服务时长可能为空，需要兜底）。
        """
        stmt = (
            select(Order)
            .join(OrderAssignment, OrderAssignment.order_id == Order.id)
            .options(selectinload(Order.service))
            .where(
                OrderAssignment.staff_id == staff_id,
                OrderAssignment.status.in_(
                    (AssignmentStatus.ASSIGNED, AssignmentStatus.ACCEPTED)
                ),
                Order.status.in_((OrderStatus.ASSIGNED, OrderStatus.IN_SERVICE)),
                Order.scheduled_at >= window_start,
                Order.scheduled_at < window_end,
            )
        )
        if exclude_order_id is not None:
            stmt = stmt.where(Order.id != exclude_order_id)
        return list(self._db.scalars(stmt).all())

    # ------------------------------------------------------------ 候选员工
    def candidate_staff(self) -> list[tuple[User, StaffProfile | None]]:
        """一次取出全部员工与排班档案，跨站点也带上，由规则层给出排除原因。"""
        stmt = (
            select(User, StaffProfile)
            .outerjoin(StaffProfile, StaffProfile.user_id == User.id)
            .options(selectinload(User.station))
            .where(User.role == Role.STAFF)
            .order_by(User.id)
        )
        return [(user, profile) for user, profile in self._db.execute(stmt).all()]

    def staff_on_leave(self, staff_ids: list[int], leave_date: date) -> set[int]:
        if not staff_ids:
            return set()
        rows = self._db.scalars(
            select(StaffLeave.staff_id).where(
                StaffLeave.staff_id.in_(staff_ids),
                StaffLeave.leave_date == leave_date,
            )
        ).all()
        return {int(staff_id) for staff_id in rows}

    def staff_day_loads(
        self,
        staff_ids: list[int],
        *,
        day_start: datetime,
        day_end: datetime,
        exclude_order_id: int | None = None,
    ) -> dict[int, int]:
        """目标业务日内已派且未结束的订单数（按订单去重，避免重派重复计数）。"""
        if not staff_ids:
            return {}
        stmt = (
            select(OrderAssignment.staff_id, func.count(func.distinct(Order.id)))
            .join(Order, Order.id == OrderAssignment.order_id)
            .where(
                OrderAssignment.staff_id.in_(staff_ids),
                OrderAssignment.status.in_(
                    (AssignmentStatus.ASSIGNED, AssignmentStatus.ACCEPTED)
                ),
                Order.status.in_((OrderStatus.ASSIGNED, OrderStatus.IN_SERVICE)),
                Order.scheduled_at >= day_start,
                Order.scheduled_at < day_end,
            )
            .group_by(OrderAssignment.staff_id)
        )
        if exclude_order_id is not None:
            stmt = stmt.where(Order.id != exclude_order_id)
        rows = self._db.execute(stmt).all()
        return {int(staff_id): int(count) for staff_id, count in rows}

    def staff_busy_slots(
        self,
        staff_ids: list[int],
        *,
        window_start: datetime,
        window_end: datetime,
        exclude_order_id: int | None = None,
    ) -> dict[int, list[Order]]:
        """按员工分组返回时间窗内已占用时段的订单（已派/已接/服务中）。"""
        if not staff_ids:
            return {}
        stmt = (
            select(OrderAssignment.staff_id, Order)
            .join(Order, Order.id == OrderAssignment.order_id)
            .options(selectinload(Order.service))
            .where(
                OrderAssignment.staff_id.in_(staff_ids),
                OrderAssignment.status.in_(
                    (AssignmentStatus.ASSIGNED, AssignmentStatus.ACCEPTED)
                ),
                Order.status.in_((OrderStatus.ASSIGNED, OrderStatus.IN_SERVICE)),
                Order.scheduled_at >= window_start,
                Order.scheduled_at < window_end,
            )
        )
        if exclude_order_id is not None:
            stmt = stmt.where(Order.id != exclude_order_id)
        grouped: dict[int, list[Order]] = {}
        for staff_id, order in self._db.execute(stmt).all():
            grouped.setdefault(int(staff_id), []).append(order)
        return grouped

    def list_reviews(self, limit: int = 100) -> list[Review]:
        return list(self._db.scalars(select(Review).order_by(Review.id.desc()).limit(limit)).all())

    def list_reviews_with_context(self, limit: int = 100) -> list[Review]:
        """后台评价列表：一次性带出订单、老人与服务项，避免逐行查询。"""
        stmt = (
            select(Review)
            .options(
                selectinload(Review.order).selectinload(Order.elder),
                selectinload(Review.order).selectinload(Order.service),
            )
            .order_by(Review.id.desc())
            .limit(limit)
        )
        return list(self._db.scalars(stmt).all())

    def count_by_status(self, status: str) -> int:
        return (
            self._db.scalar(select(func.count()).select_from(Order).where(Order.status == status))
            or 0
        )

    def count_since(self, start: datetime, statuses: tuple[str, ...]) -> int:
        """统计 ``status_changed_at`` 落在 start 之后、且处于指定状态的订单数。"""
        return (
            self._db.scalar(
                select(func.count())
                .select_from(Order)
                .where(Order.status.in_(statuses), Order.status_changed_at >= start)
            )
            or 0
        )

    def count_dispatched_since(self, start: datetime) -> int:
        """今日派单动作数（按订单去重，改派不重复计）。"""
        return (
            self._db.scalar(
                select(func.count(func.distinct(OrderAssignment.order_id))).where(
                    OrderAssignment.assigned_at >= start
                )
            )
            or 0
        )
