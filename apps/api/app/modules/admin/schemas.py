from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class StatsOut(BaseModel):
    today_orders: int
    pending_confirm: int
    assigned: int
    in_service: int
    completed_today: int
    revenue_cents: int
    total_customers: int
    total_elders: int


class AdminReviewOut(BaseModel):
    id: int
    order_id: int
    order_no: str = ""
    elder_name: str = ""
    service_name: str = ""
    rating: int
    content: str
    created_at: datetime


class AuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    actor_id: int | None = None
    action: str
    entity: str
    entity_id: int | None = None
    payload: dict
    created_at: datetime
