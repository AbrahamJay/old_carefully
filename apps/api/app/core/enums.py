"""领域枚举。

全部继承 StrEnum，因此可以直接与数据库中的字符串比较，
也可以直接传递给 Pydantic / SQLAlchemy 而无需转换。
"""

from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    ADMIN = "admin"
    CUSTOMER = "customer"
    STAFF = "staff"


class UserStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"


class OrderStatus(StrEnum):
    PENDING_CONFIRM = "pending_confirm"
    CONFIRMED = "confirmed"
    ASSIGNED = "assigned"
    IN_SERVICE = "in_service"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class AssignmentStatus(StrEnum):
    ASSIGNED = "assigned"
    ACCEPTED = "accepted"
    COMPLETED = "completed"
    REJECTED = "rejected"


class PaymentStatus(StrEnum):
    UNPAID = "unpaid"
    DEPOSIT_PAID = "deposit_paid"
    PAID_MOCK = "paid_mock"
    PAID_OFFLINE = "paid_offline"
    REFUNDED = "refunded"


class PaymentRecordStatus(StrEnum):
    PAID = "paid"
    REFUNDED = "refunded"


class PaymentProvider(StrEnum):
    MOCK = "mock"
    OFFLINE = "offline"
    WECHAT = "wechat"


class ConsentType(StrEnum):
    SERVICE = "service"


class NotificationType(StrEnum):
    SYSTEM = "system"
    ORDER_CREATED = "order_created"
    ORDER_CONFIRMED = "order_confirmed"
    ORDER_ASSIGNED = "order_assigned"
    ORDER_STARTED = "order_started"
    ORDER_COMPLETED = "order_completed"
    ORDER_CANCELLED = "order_cancelled"
    ORDER_PAID = "order_paid"
    ORDER_REFUNDED = "order_refunded"


class StaffStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"


class StorageProvider(StrEnum):
    LOCAL = "local"
    MINIO = "minio"


class BindingStatus(StrEnum):
    ACTIVE = "active"
    REVOKED = "revoked"
