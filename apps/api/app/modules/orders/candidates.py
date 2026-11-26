"""候选员工规则引擎。

纯函数：入参是已经加载好的结构快照，不碰数据库，便于单测。
硬过滤顺序与打分口径见《Agent数据底座概要设计》5.4：
规则负责事实，AI 只负责表达。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, tzinfo

from ...domain.order_time import intervals_overlap

# 打分权重，总分 100
SKILL_SCORE = 40
AVAILABILITY_SCORE = 20
LOAD_SCORE = 20
RATING_SCORE = 10
COMMUNITY_SCORE = 10

# 员工缺档案时的兜底，与数据库 server_default 保持一致
DEFAULT_WORK_DAYS = (1, 2, 3, 4, 5, 6, 7)
DEFAULT_WORK_START_MINUTE = 480
DEFAULT_WORK_END_MINUTE = 1080
DEFAULT_DAILY_CAPACITY = 4


@dataclass(frozen=True)
class TimeSlot:
    """员工已被占用的时段（左闭右开）。"""

    start: datetime
    end: datetime
    order_no: str = ""


@dataclass(frozen=True)
class OrderContext:
    """目标订单的派单上下文，全部按业务时区换算好。"""

    order_id: int
    station_id: int | None
    required_skill: str | None
    start: datetime
    end: datetime
    tz: tzinfo
    business_date: date
    weekday: int
    start_minute: int
    end_minute: int
    same_day: bool
    elder_community: str


@dataclass(frozen=True)
class StaffSnapshot:
    """候选判断所需的员工快照。"""

    staff_id: int
    name: str
    station_id: int | None
    station_name: str
    station_address: str
    skills: tuple[str, ...]
    rating: float
    user_active: bool
    profile_active: bool
    profile_present: bool
    accepting_orders: bool
    work_days: tuple[int, ...]
    work_start_minute: int
    work_end_minute: int
    daily_capacity: int
    on_leave: bool
    load: int
    busy: tuple[TimeSlot, ...]


@dataclass(frozen=True)
class Candidate:
    staff_id: int
    name: str
    station_id: int | None
    station_name: str
    skills: tuple[str, ...]
    rating: float
    score: int
    load: int
    capacity: int
    reasons: tuple[str, ...]
    risks: tuple[str, ...]


@dataclass(frozen=True)
class ExcludedCandidate:
    staff_id: int
    name: str
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class Evaluation:
    candidates: tuple[Candidate, ...]
    excluded: tuple[ExcludedCandidate, ...]
    data_gaps: tuple[str, ...]


@dataclass(frozen=True)
class CandidateReport:
    order_id: int
    generated_at: datetime
    required_skill: str | None
    candidates: tuple[Candidate, ...]
    excluded: tuple[ExcludedCandidate, ...]
    data_gaps: tuple[str, ...]


def _fmt_minute(minute: int) -> str:
    minute = max(0, min(int(minute), 24 * 60))
    return f"{minute // 60:02d}:{minute % 60:02d}"


def _fmt_slot(start: datetime, end: datetime, tz: tzinfo) -> str:
    local_start = start.astimezone(tz)
    local_end = end.astimezone(tz)
    return f"{local_start.strftime('%m-%d %H:%M')}-{local_end.strftime('%H:%M')}"


def _same_community(ctx: OrderContext, staff: StaffSnapshot) -> bool:
    """MVP 口径：老人社区名出现在员工站点名称/地址中即视为同社区。

    站点目前没有独立的 community 字段，等以后拆站点层级再替换这里。
    """
    community = ctx.elder_community.strip()
    if not community:
        return False
    return community in staff.station_name or community in staff.station_address


def _exclusion(ctx: OrderContext, staff: StaffSnapshot) -> str | None:
    """按设计文档顺序执行硬过滤，返回第一条命中的排除原因。"""
    if ctx.station_id is None or staff.station_id != ctx.station_id:
        return "非本社区（站点不同）"
    if not staff.user_active:
        return "账号已停用"
    if not staff.profile_active:
        return "员工档案已停用"
    if not staff.accepting_orders:
        return "已暂停接单"
    if ctx.required_skill and ctx.required_skill not in staff.skills:
        return f"技能不匹配（需{ctx.required_skill}）"
    if ctx.weekday not in staff.work_days:
        return "当日非工作日"
    if not ctx.same_day:
        return "跨天服务超出单日排班"
    if (
        ctx.start_minute < staff.work_start_minute
        or ctx.end_minute > staff.work_end_minute
    ):
        return (
            "超出工作时间"
            f"（{_fmt_minute(staff.work_start_minute)}-{_fmt_minute(staff.work_end_minute)}）"
        )
    if staff.on_leave:
        return "当日请假"
    for slot in staff.busy:
        if intervals_overlap(ctx.start, ctx.end, slot.start, slot.end):
            label = f"订单 {slot.order_no} " if slot.order_no else ""
            return f"时间冲突（{label}{_fmt_slot(slot.start, slot.end, ctx.tz)}）"
    if staff.daily_capacity <= 0:
        return "未设置每日容量"
    if staff.load >= staff.daily_capacity:
        return f"当日已满（{staff.load}/{staff.daily_capacity}）"
    return None


def _build_candidate(ctx: OrderContext, staff: StaffSnapshot) -> Candidate:
    same_community = _same_community(ctx, staff)
    load_ratio = staff.load / staff.daily_capacity if staff.daily_capacity > 0 else 0.0
    score = (
        SKILL_SCORE
        + AVAILABILITY_SCORE
        + round((1 - load_ratio) * LOAD_SCORE)
        + round(staff.rating / 5 * RATING_SCORE)
        + (COMMUNITY_SCORE if same_community else 0)
    )
    score = max(0, min(100, score))

    reasons = [
        "同社区" if same_community else "同站点，非同社区",
        f"技能匹配：{ctx.required_skill}" if ctx.required_skill else "服务未配置所需技能",
        f"可用：{_fmt_slot(ctx.start, ctx.end, ctx.tz)}",
        f"负载 {staff.load}/{staff.daily_capacity}",
        f"评分 {staff.rating:.1f}",
    ]

    risks: list[str] = []
    if not same_community and ctx.elder_community.strip():
        risks.append("非同社区，需跨小区出行")
    if staff.rating < 4.5:
        risks.append(f"历史评分偏低（{staff.rating:.1f}）")
    if staff.daily_capacity > 0 and staff.load >= staff.daily_capacity - 1:
        risks.append("当日接近满负荷")
    if not staff.profile_present:
        risks.append("未维护排班档案，按默认 08:00-18:00 计算")

    return Candidate(
        staff_id=staff.staff_id,
        name=staff.name,
        station_id=staff.station_id,
        station_name=staff.station_name,
        skills=staff.skills,
        rating=staff.rating,
        score=score,
        load=staff.load,
        capacity=staff.daily_capacity,
        reasons=tuple(reasons),
        risks=tuple(risks),
    )


def _data_gaps(ctx: OrderContext, staffs: tuple[StaffSnapshot, ...]) -> list[str]:
    gaps: list[str] = []
    if not ctx.required_skill:
        gaps.append("该服务未配置所需技能，未做技能过滤")
    if not ctx.elder_community.strip():
        gaps.append("老人未维护社区，同社区加分统一为 0")
    same_station = [
        staff
        for staff in staffs
        if ctx.station_id is not None and staff.station_id == ctx.station_id
    ]
    if not same_station:
        gaps.append("本社区暂无员工档案")
    missing = [staff for staff in same_station if not staff.profile_present]
    if missing:
        gaps.append(f"{len(missing)} 名员工未维护排班档案，按默认 08:00-18:00 计算")
    if not ctx.same_day:
        gaps.append("订单为跨天服务，无法匹配单日排班，员工会全部被排除")
    return gaps


def evaluate(ctx: OrderContext, staffs: tuple[StaffSnapshot, ...]) -> Evaluation:
    """执行硬过滤、打分与排序；同分按评分降序、staff_id 升序。"""
    candidates: list[Candidate] = []
    excluded: list[ExcludedCandidate] = []
    for staff in staffs:
        reason = _exclusion(ctx, staff)
        if reason is not None:
            excluded.append(
                ExcludedCandidate(staff_id=staff.staff_id, name=staff.name, reasons=(reason,))
            )
            continue
        candidates.append(_build_candidate(ctx, staff))

    candidates.sort(key=lambda item: (-item.score, -item.rating, item.staff_id))
    excluded.sort(key=lambda item: item.staff_id)
    return Evaluation(
        candidates=tuple(candidates),
        excluded=tuple(excluded),
        data_gaps=tuple(_data_gaps(ctx, staffs)),
    )
