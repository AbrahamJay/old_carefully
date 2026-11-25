"""运营看板：统计口径集中在此，避免散落在各个路由里。"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...core.enums import OrderStatus, PaymentStatus, Role
from ...core.time import business_today_start_utc
from ...db.models import AuditLog, Elder, Order, User
from ..audit import AuditService
from ..orders.repository import OrderRepository
from .schemas import AdminReviewOut, StatsOut


class AdminService:
    def __init__(self, db: Session, orders: OrderRepository, audit: AuditService) -> None:
        self._db = db
        self._orders = orders
        self._audit = audit

    def stats(self) -> StatsOut:
        today_start = business_today_start_utc()
        revenue_cents = self._db.scalar(
            select(func.coalesce(func.sum(Order.amount_cents), 0)).where(
                Order.payment_status.in_((PaymentStatus.PAID_OFFLINE, PaymentStatus.PAID_MOCK))
            )
        )
        return StatsOut(
            today_orders=self._count_orders(Order.created_at >= today_start),
            pending_confirm=self._count_orders(Order.status == OrderStatus.PENDING_CONFIRM),
            assigned=self._count_orders(Order.status == OrderStatus.ASSIGNED),
            in_service=self._count_orders(Order.status == OrderStatus.IN_SERVICE),
            completed_today=self._count_orders(
                Order.status == OrderStatus.COMPLETED,
                Order.updated_at >= today_start,
            ),
            revenue_cents=int(revenue_cents or 0),
            total_customers=self._scalar(
                select(func.count()).select_from(User).where(User.role == Role.CUSTOMER)
            ),
            total_elders=self._scalar(select(func.count()).select_from(Elder)),
        )

    def reviews(self, limit: int = 100) -> list[AdminReviewOut]:
        result: list[AdminReviewOut] = []
        for review in self._orders.list_reviews_with_context(limit):
            order = review.order
            result.append(
                AdminReviewOut(
                    id=review.id,
                    order_id=review.order_id,
                    order_no=order.order_no if order else "",
                    elder_name=order.elder.name if order and order.elder else "",
                    service_name=order.service.name if order and order.service else "",
                    rating=review.rating,
                    content=review.content,
                    created_at=review.created_at,
                )
            )
        return result

    def audit_logs(self, limit: int = 100) -> list[AuditLog]:
        return self._audit.list_recent(limit)

    # ------------------------------------------------------------------ 内部
    def _count_orders(self, *conditions) -> int:
        return self._scalar(select(func.count()).select_from(Order).where(*conditions))

    def _scalar(self, stmt) -> int:
        return int(self._db.scalar(stmt) or 0)
