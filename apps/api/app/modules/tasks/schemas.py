"""异常巡检接口的请求/响应模型。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class TaskOut(BaseModel):
    id: int
    type: str
    severity: str
    status: str
    title: str
    order_id: int
    # 订单事实直接从关联带出，前端不必再拉一次订单详情
    order_no: str = ""
    elder_name: str = ""
    service_name: str = ""
    scheduled_at: datetime | None = None
    station_name: str = ""
    order_status: str = ""
    detail: dict = Field(default_factory=dict)
    detected_at: datetime
    snoozed_until: datetime | None = None
    handled_by: int | None = None
    handled_at: datetime | None = None
    note: str = ""
    updated_at: datetime


class TaskListOut(BaseModel):
    items: list[TaskOut]
    total: int


class TaskSummaryOut(BaseModel):
    """异常巡检页顶部指标，全部由后端实时统计。"""

    open: int = 0
    high: int = 0
    handled_today: int = 0
    avg_handle_minutes: int = 0
    scan_interval_minutes: int = 10
    scan_enabled: bool = True
    last_scan_at: datetime | None = None
    by_type: dict[str, int] = Field(default_factory=dict)


class HandleIn(BaseModel):
    # 文档要求「标记已处理」必须记录操作人和备注
    note: str = Field(min_length=1, max_length=200)


class SnoozeIn(BaseModel):
    # 默认 2 小时；必须有到期时间，不能永久隐藏
    hours: float = Field(default=2, ge=0.5, le=72)
    note: str = Field(default="", max_length=200)


class IgnoreIn(BaseModel):
    reason: str = Field(min_length=1, max_length=200)


class ScanResultOut(BaseModel):
    scanned: bool = True
    detected: int = 0
    created: int = 0
    updated: int = 0
    resolved: int = 0
    duration_ms: int = 0
    skip_reason: str = ""
