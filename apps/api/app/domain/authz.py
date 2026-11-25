"""访问控制策略。

关键点：这里是"谁能看到哪个资源"的唯一实现。
列表接口与详情接口都复用同一组子查询，避免各写一套导致口径不一致。
"""

from __future__ import annotations

from sqlalchemy import Select, false, select
from sqlalchemy.orm import Session

from ..core.enums import AssignmentStatus, BindingStatus, Role
from ..db.models import Elder, FamilyBinding, Order, OrderAssignment, User

# 员工可见的派单状态（与"可见老人/可见订单"保持一致）
STAFF_VISIBLE_ASSIGNMENT_STATUSES: tuple[str, ...] = (
    AssignmentStatus.ASSIGNED,
    AssignmentStatus.ACCEPTED,
    AssignmentStatus.COMPLETED,
)


def user_elder_ids(db: Session, user_id: int) -> list[int]:
    rows = db.scalars(
        select(FamilyBinding.elder_id).where(
            FamilyBinding.user_id == user_id,
            FamilyBinding.status == BindingStatus.ACTIVE,
        )
    ).all()
    return list(rows)


def elder_visible_ids_stmt(user: User) -> Select | None:
    """返回可见老人 id 子查询；``None`` 表示不限制（管理员）。"""
    if user.role == Role.ADMIN:
        return None
    if user.role == Role.CUSTOMER:
        return select(FamilyBinding.elder_id).where(
            FamilyBinding.user_id == user.id,
            FamilyBinding.status == BindingStatus.ACTIVE,
        )
    if user.role == Role.STAFF:
        return (
            select(Order.elder_id)
            .join(OrderAssignment, OrderAssignment.order_id == Order.id)
            .where(
                OrderAssignment.staff_id == user.id,
                OrderAssignment.status.in_(STAFF_VISIBLE_ASSIGNMENT_STATUSES),
            )
            .distinct()
        )
    return select(Elder.id).where(false())


def staff_order_ids_stmt(user_id: int) -> Select:
    return select(OrderAssignment.order_id).where(
        OrderAssignment.staff_id == user_id,
        OrderAssignment.status.in_(STAFF_VISIBLE_ASSIGNMENT_STATUSES),
    )


def order_query_for_user(user: User) -> Select:
    """按角色收敛订单查询范围。"""
    stmt = select(Order)
    if user.role == Role.CUSTOMER:
        stmt = stmt.where(Order.customer_id == user.id)
    elif user.role == Role.STAFF:
        stmt = stmt.where(Order.id.in_(staff_order_ids_stmt(user.id)))
    elif user.role != Role.ADMIN:
        stmt = stmt.where(false())
    return stmt


def can_access_elder(db: Session, user: User, elder_id: int) -> bool:
    stmt = elder_visible_ids_stmt(user)
    if stmt is None:
        return True
    return (
        db.scalars(select(Elder.id).where(Elder.id == elder_id, Elder.id.in_(stmt))).first()
        is not None
    )


def can_access_order(db: Session, user: User, order: Order) -> bool:
    if user.role == Role.ADMIN:
        return True
    if user.role == Role.CUSTOMER:
        return order.customer_id == user.id
    if user.role == Role.STAFF:
        return get_staff_assignment(db, order.id, user.id) is not None
    return False


def can_access_loaded_order(user: User, order: Order) -> bool:
    """基于已预加载的 assignments 判断，避免额外查询。"""
    if user.role == Role.ADMIN:
        return True
    if user.role == Role.CUSTOMER:
        return order.customer_id == user.id
    if user.role == Role.STAFF:
        return any(
            assignment.staff_id == user.id
            and assignment.status in STAFF_VISIBLE_ASSIGNMENT_STATUSES
            for assignment in order.assignments
        )
    return False


def get_staff_assignment(
    db: Session,
    order_id: int,
    staff_id: int,
    *,
    statuses: tuple[str, ...] | None = (AssignmentStatus.ASSIGNED, AssignmentStatus.ACCEPTED),
) -> OrderAssignment | None:
    stmt = select(OrderAssignment).where(
        OrderAssignment.order_id == order_id,
        OrderAssignment.staff_id == staff_id,
    )
    if statuses:
        stmt = stmt.where(OrderAssignment.status.in_(statuses))
    return db.scalars(stmt.order_by(OrderAssignment.id.desc())).first()


def latest_assignment(
    db: Session,
    order_id: int,
    *,
    statuses: tuple[str, ...] | None = None,
) -> OrderAssignment | None:
    stmt = select(OrderAssignment).where(OrderAssignment.order_id == order_id)
    if statuses:
        stmt = stmt.where(OrderAssignment.status.in_(statuses))
    return db.scalars(stmt.order_by(OrderAssignment.id.desc())).first()
