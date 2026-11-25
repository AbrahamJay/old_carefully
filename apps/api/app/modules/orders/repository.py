from __future__ import annotations

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session, selectinload

from ...core.enums import AssignmentStatus
from ...db.models import (
    Elder,
    Order,
    OrderAssignment,
    Review,
    ServiceRecord,
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
