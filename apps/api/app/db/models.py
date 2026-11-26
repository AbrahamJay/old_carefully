"""ORM 模型。

模型集中在一个模块中：跨模块共享的实体（User / Elder / Order）如果按领域拆分，
会引入大量互相的 TYPE_CHECKING 引用，收益低于成本。
领域逻辑请放在 ``app/modules/<domain>/`` 中。
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..core.enums import StorageProvider, TaskStatus
from ..core.time import utcnow
from .base import Base


def _json_type() -> JSONB:
    """统一使用 PG 的 ``jsonb``：可建 GIN 索引、自动去重。"""
    return JSONB()


__all__ = [
    "AdminTask",
    "AgentAction",
    "AuditLog",
    "Consent",
    "Elder",
    "FamilyBinding",
    "Notification",
    "Order",
    "OrderAssignment",
    "Payment",
    "Review",
    "Service",
    "ServiceRecord",
    "StaffLeave",
    "StaffProfile",
    "Station",
    "Supplier",
    "UploadedFile",
    "User",
    "utcnow",
]


class Station(Base):
    __tablename__ = "stations"
    # 站点名作为业务键：基础数据 SQL 靠它判重，并发建站也不会插出重名
    __table_args__ = (UniqueConstraint("name", name="uq_stations_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    street: Mapped[str] = mapped_column(String(100), default="")
    address: Mapped[str] = mapped_column(String(255), default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    openid: Mapped[str | None] = mapped_column(String(128), unique=True, nullable=True)
    phone: Mapped[str | None] = mapped_column(String(20), unique=True, nullable=True)
    name: Mapped[str] = mapped_column(String(50), default="")
    role: Mapped[str] = mapped_column(String(20), default="customer", index=True)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active")
    # 站点是外键，不给默认值：空库（AUTO_SEED=false）时写死 1 会直接撞外键
    station_id: Mapped[int | None] = mapped_column(ForeignKey("stations.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    station: Mapped[Station | None] = relationship()

    @property
    def station_name(self) -> str:
        return self.station.name if self.station else ""


class StaffProfile(Base):
    __tablename__ = "staff_profiles"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    supplier_id: Mapped[int | None] = mapped_column(ForeignKey("suppliers.id"), nullable=True)
    skills: Mapped[list[str]] = mapped_column(_json_type(), default=list)
    rating: Mapped[float] = mapped_column(Float, default=5.0)
    status: Mapped[str] = mapped_column(String(20), default="active")

    # 可用性：MVP 只做「工作日 + 固定起止时间 + 每日容量」，多班次留到后续拆表。
    # work_days 用 ISO 星期：1=周一 … 7=周日；时间用「当天第几分钟」，避免时区歧义。
    work_days: Mapped[list[int]] = mapped_column(
        _json_type(),
        default=lambda: [1, 2, 3, 4, 5, 6, 7],
        server_default=text("'[1,2,3,4,5,6,7]'::jsonb"),
    )
    work_start_minute: Mapped[int] = mapped_column(Integer, default=480, server_default="480")
    work_end_minute: Mapped[int] = mapped_column(Integer, default=1080, server_default="1080")
    daily_capacity: Mapped[int] = mapped_column(Integer, default=4, server_default="4")
    accepting_orders: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true")
    )

    user: Mapped[User] = relationship()
    supplier: Mapped[Supplier | None] = relationship()


class StaffLeave(Base):
    """员工请假：按天粒度，命中当天即不参与候选。"""

    __tablename__ = "staff_leaves"
    __table_args__ = (
        UniqueConstraint("staff_id", "leave_date", name="uq_staff_leaves_staff_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    staff_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    leave_date: Mapped[date] = mapped_column(Date, nullable=False)
    reason: Mapped[str] = mapped_column(String(100), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    staff: Mapped[User] = relationship()


class Supplier(Base):
    __tablename__ = "suppliers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    category: Mapped[str] = mapped_column(String(50), default="cleaning")
    contact_name: Mapped[str] = mapped_column(String(50), default="")
    contact_phone: Mapped[str] = mapped_column(String(20), default="")
    contract_status: Mapped[str] = mapped_column(String(20), default="signed")
    insurance_status: Mapped[str] = mapped_column(String(20), default="valid")
    rating: Mapped[float] = mapped_column(Float, default=5.0)


class Elder(Base):
    __tablename__ = "elders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    station_id: Mapped[int] = mapped_column(ForeignKey("stations.id"), default=1, index=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    gender: Mapped[str] = mapped_column(String(10), default="unknown")
    birth_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    phone: Mapped[str] = mapped_column(String(20), default="")
    address: Mapped[str] = mapped_column(String(255), default="")
    community: Mapped[str] = mapped_column(String(100), default="")
    health_notes: Mapped[str] = mapped_column(Text, default="")
    emergency_name: Mapped[str] = mapped_column(String(50), default="")
    emergency_phone: Mapped[str] = mapped_column(String(20), default="")
    invite_code: Mapped[str | None] = mapped_column(String(20), unique=True, nullable=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    station: Mapped[Station] = relationship()
    bindings: Mapped[list[FamilyBinding]] = relationship(back_populates="elder")

    @property
    def station_name(self) -> str:
        return self.station.name if self.station else ""


class FamilyBinding(Base):
    __tablename__ = "family_bindings"
    __table_args__ = (UniqueConstraint("user_id", "elder_id", name="uq_binding_user_elder"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    elder_id: Mapped[int] = mapped_column(ForeignKey("elders.id"), index=True)
    relation: Mapped[str] = mapped_column(String(20), default="family")
    status: Mapped[str] = mapped_column(String(20), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped[User] = relationship()
    elder: Mapped[Elder] = relationship(back_populates="bindings")


class Service(Base):
    __tablename__ = "services"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(30), unique=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    category: Mapped[str] = mapped_column(String(30), default="companion")
    description: Mapped[str] = mapped_column(Text, default="")
    price_cents: Mapped[int] = mapped_column(Integer, default=0)
    duration_minutes: Mapped[int] = mapped_column(Integer, default=60)
    unit: Mapped[str] = mapped_column(String(20), default="次")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort: Mapped[int] = mapped_column(Integer, default=0)
    # 派单所需的技能映射；为空表示未配置，候选时不做技能硬过滤但会标记数据缺口
    required_skill: Mapped[str | None] = mapped_column(String(30), nullable=True)


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (
        # 异常巡检按「状态 + 停留时长」扫描，updated_at 会被任意字段刷新，不能替代
        Index("ix_orders_status_status_changed_at", "status", "status_changed_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_no: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    station_id: Mapped[int] = mapped_column(ForeignKey("stations.id"), default=1, index=True)
    elder_id: Mapped[int] = mapped_column(ForeignKey("elders.id"), index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    service_id: Mapped[int] = mapped_column(ForeignKey("services.id"))
    status: Mapped[str] = mapped_column(String(30), default="pending_confirm", index=True)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    address: Mapped[str] = mapped_column(String(255), default="")
    contact_name: Mapped[str] = mapped_column(String(50), default="")
    contact_phone: Mapped[str] = mapped_column(String(20), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    amount_cents: Mapped[int] = mapped_column(Integer, default=0)
    deposit_cents: Mapped[int] = mapped_column(Integer, default=0)
    payment_status: Mapped[str] = mapped_column(String(30), default="unpaid", index=True)
    cancel_reason: Mapped[str] = mapped_column(String(255), default="")
    # 仅在订单状态真正变化时刷新；改地址/备注等字段不刷新
    status_changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=text("now()")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    elder: Mapped[Elder] = relationship()
    customer: Mapped[User] = relationship()
    service: Mapped[Service] = relationship()
    station: Mapped[Station] = relationship()
    assignments: Mapped[list[OrderAssignment]] = relationship(
        back_populates="order",
        cascade="all, delete-orphan",
        order_by="OrderAssignment.id",
    )
    records: Mapped[list[ServiceRecord]] = relationship(
        back_populates="order",
        cascade="all, delete-orphan",
        order_by="ServiceRecord.id",
    )
    payments: Mapped[list[Payment]] = relationship(
        back_populates="order", cascade="all, delete-orphan"
    )
    review: Mapped[Review | None] = relationship(back_populates="order", uselist=False)


class OrderAssignment(Base):
    __tablename__ = "order_assignments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    staff_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="assigned")
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    order: Mapped[Order] = relationship(back_populates="assignments")
    staff: Mapped[User] = relationship()


class ServiceRecord(Base):
    __tablename__ = "service_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    staff_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    checkin_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    checkout_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    content: Mapped[str] = mapped_column(Text, default="")
    photos: Mapped[list[str]] = mapped_column(_json_type(), default=list)
    signature_url: Mapped[str] = mapped_column(String(255), default="")
    elder_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    order: Mapped[Order] = relationship(back_populates="records")
    staff: Mapped[User] = relationship()


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    provider: Mapped[str] = mapped_column(String(20), default="offline")
    amount_cents: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="paid", index=True)
    transaction_id: Mapped[str] = mapped_column(String(64), default="")
    paid_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    raw: Mapped[dict] = mapped_column(_json_type(), default=dict)

    order: Mapped[Order] = relationship(back_populates="payments")


class Review(Base):
    __tablename__ = "reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), unique=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    rating: Mapped[int] = mapped_column(Integer, default=5)
    content: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    order: Mapped[Order] = relationship(back_populates="review")
    customer: Mapped[User] = relationship()


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    type: Mapped[str] = mapped_column(String(40), default="system")
    title: Mapped[str] = mapped_column(String(100), default="")
    body: Mapped[str] = mapped_column(Text, default="")
    payload: Mapped[dict] = mapped_column(_json_type(), default=dict)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )


class Consent(Base):
    __tablename__ = "consents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    elder_id: Mapped[int] = mapped_column(ForeignKey("elders.id"), index=True)
    type: Mapped[str] = mapped_column(String(20), default="service")
    version: Mapped[str] = mapped_column(String(20), default="v1")
    signed_by: Mapped[str] = mapped_column(String(50), default="")
    signed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(50), default="")
    entity: Mapped[str] = mapped_column(String(50), default="")
    entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    payload: Mapped[dict] = mapped_column(_json_type(), default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )


class UploadedFile(Base):
    """上传文件元信息。

    用于给文件建立"归属关系"，从而支撑下载鉴权与后续的引用清理。
    """

    __tablename__ = "uploaded_files"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"), nullable=True, index=True)
    content_type: Mapped[str] = mapped_column(String(50), default="")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    # 记录落地的存储介质：切换 provider 后旧文件仍能从原介质读回
    storage: Mapped[str] = mapped_column(String(20), default=StorageProvider.LOCAL)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AdminTask(Base):
    """异常巡检任务队列。

    ``dedupe_key`` 由「类型 + 订单 + 状态时间」组成，同一订单同一状态只保留一条；
    扫描用 ``INSERT ... ON CONFLICT`` 刷新事实，条件消失后自动置 ``resolved``。
    """

    __tablename__ = "admin_tasks"
    __table_args__ = (
        Index("ix_admin_tasks_status_severity", "status", "severity", "detected_at"),
        Index("ix_admin_tasks_order_type", "order_id", "type", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    type: Mapped[str] = mapped_column(String(40))
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"))
    severity: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(20), default=TaskStatus.OPEN)
    dedupe_key: Mapped[str] = mapped_column(String(120), unique=True)
    title: Mapped[str] = mapped_column(String(120), default="")
    detail: Mapped[dict] = mapped_column(_json_type(), default=dict)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    snoozed_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    handled_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    handled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    note: Mapped[str] = mapped_column(String(255), default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    order: Mapped[Order] = relationship()


class AgentAction(Base):
    """Agent 调用审计：每次模型/工具/动作调用一行。

    与 ``audit_logs`` 分工不同：后者记「人对业务数据的修改」，本表记「AI 参与了什么」，
    两者不双写。``payload`` 只存白名单字段（订单号、模型、耗时等），用户输入与老人
    健康信息一律只留摘要，保证排障可用、原文不落库。
    """

    __tablename__ = "agent_actions"
    # trace_id 串起一次请求内的多个步骤；thread_id 留给阶段七的对话会话，当前恒为空。
    __table_args__ = (
        Index("ix_agent_actions_trace", "trace_id", "step"),
        Index("ix_agent_actions_user_created", "user_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    trace_id: Mapped[str] = mapped_column(String(32), index=True)
    thread_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    scenario: Mapped[str] = mapped_column(String(40))
    step: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="ok")
    model: Mapped[str] = mapped_column(String(60), default="")
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    tokens_in: Mapped[int] = mapped_column(Integer, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0)
    error_code: Mapped[str] = mapped_column(String(40), default="")
    payload: Mapped[dict] = mapped_column(_json_type(), default=dict)
    # 对输入做 SHA-256，既能比对同一输入是否重复调用，又不保存原文
    payload_digest: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )
