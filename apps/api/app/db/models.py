"""ORM 模型。

模型集中在一个模块中：跨模块共享的实体（User / Elder / Order）如果按领域拆分，
会引入大量互相的 TYPE_CHECKING 引用，收益低于成本。
领域逻辑请放在 ``app/modules/<domain>/`` 中。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..core.enums import StorageProvider
from ..core.time import utcnow
from .base import Base


def _json_type() -> JSONB:
    """统一使用 PG 的 ``jsonb``：可建 GIN 索引、自动去重。"""
    return JSONB()


__all__ = [
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

    user: Mapped[User] = relationship()
    supplier: Mapped[Supplier | None] = relationship()


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


class Order(Base):
    __tablename__ = "orders"

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
