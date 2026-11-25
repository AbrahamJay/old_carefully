from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class StationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    street: str
    address: str
    active: bool


class StationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    street: str = Field(default="", max_length=100)
    address: str = Field(default="", max_length=255)
    active: bool = True


class StationUpdate(BaseModel):
    name: str | None = None
    street: str | None = None
    address: str | None = None
    active: bool | None = None


class StaffCreate(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    phone: str = Field(min_length=6, max_length=20)
    skills: list[str] = Field(default_factory=list)
    supplier_id: int | None = None
    station_id: int | None = None


class StaffUpdate(BaseModel):
    name: str | None = None
    skills: list[str] | None = None
    status: str | None = None
    supplier_id: int | None = None
    station_id: int | None = None


class StaffOut(BaseModel):
    id: int
    name: str
    phone: str | None = None
    role: str
    skills: list[str] = Field(default_factory=list)
    rating: float = 5.0
    status: str = "active"
    station_id: int | None = None
    station_name: str = ""


class SupplierCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    category: str = "cleaning"
    contact_name: str = ""
    contact_phone: str = ""
    contract_status: str = "signed"
    insurance_status: str = "valid"


class SupplierOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    category: str
    contact_name: str
    contact_phone: str
    contract_status: str
    insurance_status: str
    rating: float
