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


class AnomalyType(StrEnum):
    """异常巡检类型，与 ``admin_tasks.type`` 一致。"""

    PENDING_TIMEOUT = "pending_timeout"
    CONFIRMED_UNASSIGNED = "confirmed_unassigned"
    ASSIGNED_NOT_ACCEPTED = "assigned_not_accepted"
    IN_SERVICE_OVERRUN = "in_service_overrun"
    BALANCE_DUE = "balance_due"
    MISSING_RECORD = "missing_record"


class TaskSeverity(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class TaskStatus(StrEnum):
    """异常任务状态：open/snoozed 会被下次扫描继续跟踪，其余为终态。"""

    OPEN = "open"
    SNOOZED = "snoozed"
    HANDLED = "handled"
    IGNORED = "ignored"
    RESOLVED = "resolved"


class AgentScenario(StrEnum):
    """Agent 场景标识，同时写入 ``agent_actions.scenario``。"""

    RECORD_DRAFT = "record_draft"
    PREP_BRIEF = "prep_brief"
    # 管理端两个场景：规则算事实，模型只负责解释，不参与决策
    DISPATCH_SUGGEST = "dispatch_suggest"
    TASK_EXPLAIN = "task_explain"
    # 员工「这单助手」：绑定单张订单的窄问答，不是通用助手
    CHAT = "chat"


class AgentActionStatus(StrEnum):
    """单次 Agent 调用的结果：失败也要落库，否则无法统计可用率。"""

    OK = "ok"
    FAILED = "failed"
    BLOCKED = "blocked"
