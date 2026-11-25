from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ElderCreate(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    gender: str = "unknown"
    birth_year: int | None = None
    phone: str = ""
    address: str = ""
    community: str = ""
    health_notes: str = ""
    emergency_name: str = ""
    emergency_phone: str = ""
    station_id: int | None = None


class ElderUpdate(BaseModel):
    name: str | None = None
    gender: str | None = None
    birth_year: int | None = None
    phone: str | None = None
    address: str | None = None
    community: str | None = None
    health_notes: str | None = None
    emergency_name: str | None = None
    emergency_phone: str | None = None
    station_id: int | None = None


class ElderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    gender: str
    birth_year: int | None = None
    phone: str
    address: str
    community: str
    health_notes: str
    emergency_name: str
    emergency_phone: str
    invite_code: str | None = None
    station_id: int | None = None
    station_name: str = ""


class BindingCreate(BaseModel):
    invite_code: str = Field(min_length=4, max_length=20)
    relation: str = "family"


class BindingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    elder_id: int
    relation: str
    status: str


class BindingWithElderOut(BindingOut):
    elder: ElderOut | None = None


class ConsentCreate(BaseModel):
    type: str = "service"
    version: str = "v1"
    signed_by: str = ""


class ConsentOut(BaseModel):
    id: int
    elder_id: int
    type: str
    version: str
    signed_at: datetime


class InviteCodeOut(BaseModel):
    invite_code: str
    elder_id: int
