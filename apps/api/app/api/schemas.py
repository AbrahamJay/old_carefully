"""跨模块复用的通用出参。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class Page[ItemT](BaseModel):
    items: list[ItemT] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 20


class OkOut(BaseModel):
    ok: bool = True
