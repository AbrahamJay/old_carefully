"""时间工具。

约定：数据库与接口一律使用 UTC，只有"统计边界"这类业务语义才换算到业务时区。
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from .config import settings


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def business_tz() -> ZoneInfo:
    return ZoneInfo(settings.business_timezone)


def business_today_start_utc() -> datetime:
    """业务时区"今天 00:00"对应的 UTC 时间点。"""
    return business_day_start_utc()


def business_day_start_utc(offset_days: int = 0, today: date | None = None) -> datetime:
    """业务时区第 ``offset_days`` 天（0=今天）00:00 对应的 UTC 时间点。

    参数 ``today`` 用于测试固定基准日，避免依赖真实时钟。
    """
    base = today or datetime.now(business_tz()).date()
    local_day = base + timedelta(days=offset_days)
    local_start = datetime.combine(local_day, time.min, tzinfo=business_tz())
    return local_start.astimezone(timezone.utc)
