from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    phone: str | None = None
    role: str
    station_id: int | None = None
    station_name: str = ""


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class LoginIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    phone: str = Field(min_length=6, max_length=20)
    password: str = Field(min_length=6, max_length=100)


class AdminLoginIn(BaseModel):
    username: str = Field(min_length=3, max_length=30)
    password: str = Field(min_length=6, max_length=100)


class WechatLoginIn(BaseModel):
    code: str = ""
    mock_openid: str | None = None
