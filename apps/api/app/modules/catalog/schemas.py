from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ServiceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    category: str
    description: str
    price_cents: int
    duration_minutes: int
    unit: str
    active: bool
    sort: int
    required_skill: str | None = None


class ServiceCreate(BaseModel):
    code: str = Field(min_length=1, max_length=30)
    name: str = Field(min_length=1, max_length=50)
    category: str = "companion"
    description: str = ""
    price_cents: int = Field(default=0, ge=0)
    duration_minutes: int = Field(default=60, ge=0)
    unit: str = "次"
    active: bool = True
    sort: int = 0
    # 派单所需的员工技能；留空表示未配置，候选时不做技能硬过滤
    required_skill: str | None = Field(default=None, max_length=30)
