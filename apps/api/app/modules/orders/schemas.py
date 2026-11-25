from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from ..auth.schemas import UserOut
from ..catalog.schemas import ServiceOut
from ..elders.schemas import ElderOut


class OrderCreate(BaseModel):
    elder_id: int
    service_id: int
    scheduled_at: datetime
    address: str = ""
    contact_name: str = ""
    contact_phone: str = ""
    notes: str = ""


class OrderListItem(BaseModel):
    id: int
    order_no: str
    status: str
    payment_status: str
    service_name: str
    elder_name: str
    staff_name: str = ""
    station_id: int | None = None
    station_name: str = ""
    deposit_cents: int = 0
    paid_cents: int = 0
    remaining_cents: int = 0
    service_confirmed: bool = False
    scheduled_at: datetime
    amount_cents: int
    created_at: datetime


class RecordCreate(BaseModel):
    content: str = Field(default="", max_length=2000)
    photos: list[str] = Field(default_factory=list)
    checkin_at: datetime | None = None
    elder_confirmed: bool = False


class RecordOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    order_id: int
    staff_id: int
    checkin_at: datetime
    checkout_at: datetime | None = None
    content: str
    photos: list[str]
    elder_confirmed: bool
    created_at: datetime


class ReviewCreate(BaseModel):
    rating: int = Field(ge=1, le=5)
    content: str = Field(default="", max_length=1000)


class ReviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    order_id: int
    rating: int
    content: str
    created_at: datetime


class OrderDetailOut(BaseModel):
    id: int
    order_no: str
    status: str
    payment_status: str
    scheduled_at: datetime
    address: str
    contact_name: str
    contact_phone: str
    notes: str
    amount_cents: int
    deposit_cents: int = 0
    paid_cents: int = 0
    refunded_cents: int = 0
    remaining_cents: int = 0
    service_confirmed: bool = False
    cancel_reason: str
    created_at: datetime
    updated_at: datetime
    station_id: int | None = None
    station_name: str = ""
    elder: ElderOut
    service: ServiceOut
    staff: UserOut | None = None
    records: list[RecordOut] = Field(default_factory=list)
    review: ReviewOut | None = None


class AssignIn(BaseModel):
    staff_id: int


class PaymentMarkIn(BaseModel):
    method: str = "offline"
