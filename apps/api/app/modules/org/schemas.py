from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# 单次请假最多允许一年，避免一次写入过多按天记录
MAX_LEAVE_RANGE_DAYS = 366


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
    work_days: list[int] | None = None
    work_start_minute: int | None = Field(default=None, ge=0, le=1439)
    work_end_minute: int | None = Field(default=None, ge=1, le=1440)
    daily_capacity: int | None = Field(default=None, ge=0, le=50)
    accepting_orders: bool | None = None

    @field_validator("work_days")
    @classmethod
    def _check_work_days(cls, value: list[int] | None) -> list[int] | None:
        if value is None:
            return value
        days = sorted({int(day) for day in value})
        if not days or any(day < 1 or day > 7 for day in days):
            raise ValueError("work_days 必须是 1-7 的非空集合（1=周一，7=周日）")
        return days


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
    work_days: list[int] = Field(default_factory=lambda: [1, 2, 3, 4, 5, 6, 7])
    work_start_minute: int = 480
    work_end_minute: int = 1080
    daily_capacity: int = 4
    accepting_orders: bool = True
    # 今日已派且未结束的单数，用于后台展示「负载 / 容量」
    today_load: int = 0
    # 今日是否在请假区间内（实时计算，不落库）
    on_leave_today: bool = False


class StaffLeaveCreate(BaseModel):
    start_date: date
    end_date: date | None = None
    reason: str = Field(default="", max_length=100)

    @model_validator(mode="after")
    def _check_range(self) -> StaffLeaveCreate:
        end = self.end_date or self.start_date
        if end < self.start_date:
            raise ValueError("结束日期不能早于开始日期")
        if (end - self.start_date).days + 1 > MAX_LEAVE_RANGE_DAYS:
            raise ValueError(f"单次请假不能超过 {MAX_LEAVE_RANGE_DAYS} 天")
        return self


class StaffLeaveOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    staff_id: int
    leave_date: date
    reason: str


class StaffLeaveDeleteOut(BaseModel):
    deleted: int


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
