"""时间工具。

约定：数据库与接口一律使用 UTC，只有"统计边界"这类业务语义才换算到业务时区。
"""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from .config import settings


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def business_tz() -> ZoneInfo:
    return ZoneInfo(settings.business_timezone)


def business_today_start_utc() -> datetime:
    """业务时区"今天 00:00"对应的 UTC 时间点。"""
    local_now = datetime.now(business_tz())
    local_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    return local_start.astimezone(timezone.utc)
