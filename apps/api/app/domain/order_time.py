"""订单时段规则。

把「预约时间 + 服务时长」统一换算成左闭右开区间，
派单冲突校验（本阶段）与候选排序（阶段二）共用同一套口径。
"""

from __future__ import annotations

from datetime import datetime, timedelta

# 服务时长缺失时的兜底，避免区间退化成一个点而永远不冲突
DEFAULT_DURATION_MINUTES = 30


def order_interval(
    scheduled_at: datetime,
    duration_minutes: int | None,
) -> tuple[datetime, datetime]:
    """返回订单占用的 ``[开始, 结束)`` 区间。"""
    minutes = (
        duration_minutes
        if duration_minutes is not None and duration_minutes > 0
        else DEFAULT_DURATION_MINUTES
    )
    return scheduled_at, scheduled_at + timedelta(minutes=minutes)


def intervals_overlap(
    a_start: datetime,
    a_end: datetime,
    b_start: datetime,
    b_end: datetime,
) -> bool:
    """左闭右开区间重叠判定：首尾相接（a_end == b_start）不算冲突。"""
    return a_start < b_end and b_start < a_end
