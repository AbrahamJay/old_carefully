"""订单状态机。

所有状态迁移必须经过本模块，避免各路由自行手写状态判断而出现口径分裂。
"""

from __future__ import annotations

from ..core.enums import OrderStatus
from ..core.errors import ConflictError

TRANSITIONS: dict[OrderStatus, frozenset[OrderStatus]] = {
    OrderStatus.PENDING_CONFIRM: frozenset({OrderStatus.CONFIRMED, OrderStatus.CANCELLED}),
    OrderStatus.CONFIRMED: frozenset({OrderStatus.ASSIGNED, OrderStatus.CANCELLED}),
    OrderStatus.ASSIGNED: frozenset({OrderStatus.IN_SERVICE, OrderStatus.CANCELLED}),
    OrderStatus.IN_SERVICE: frozenset({OrderStatus.COMPLETED}),
    OrderStatus.COMPLETED: frozenset(),
    OrderStatus.CANCELLED: frozenset(),
}

# 允许用户或管理员主动取消的状态
CANCELLABLE: frozenset[OrderStatus] = frozenset(
    {OrderStatus.PENDING_CONFIRM, OrderStatus.CONFIRMED, OrderStatus.ASSIGNED}
)


def can_transition(current: str, target: OrderStatus) -> bool:
    try:
        allowed = TRANSITIONS[OrderStatus(current)]
    except ValueError:
        return False
    return target in allowed


def ensure_transition(current: str, target: OrderStatus) -> None:
    if not can_transition(current, target):
        raise ConflictError(f"订单状态不能从 {current} 变为 {target}")


def ensure_cancellable(current: str) -> None:
    if current not in CANCELLABLE:
        raise ConflictError("服务开始后不能取消")
