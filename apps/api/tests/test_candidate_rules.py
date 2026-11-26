"""阶段二：候选规则引擎纯函数单测。

不连数据库：直接构造订单上下文与员工快照，覆盖硬过滤顺序、打分与 data_gaps。
"""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from app.modules.orders.candidates import (
    OrderContext,
    StaffSnapshot,
    TimeSlot,
    evaluate,
)

TZ = ZoneInfo("Asia/Shanghai")


def _ctx(**overrides) -> OrderContext:
    """2026-12-01（周二）09:00-13:00 的陪诊订单。"""
    base = {
        "order_id": 1,
        "station_id": 1,
        "required_skill": "陪诊",
        "start": datetime(2026, 12, 1, 9, 0, tzinfo=TZ),
        "end": datetime(2026, 12, 1, 13, 0, tzinfo=TZ),
        "tz": TZ,
        "business_date": date(2026, 12, 1),
        "weekday": 2,
        "start_minute": 540,
        "end_minute": 780,
        "same_day": True,
        "elder_community": "示范社区",
    }
    base.update(overrides)
    return OrderContext(**base)


def _staff(**overrides) -> StaffSnapshot:
    """默认是一名完全可用的员工。"""
    base = {
        "staff_id": 1,
        "name": "王阿姨",
        "station_id": 1,
        "station_name": "示范社区站",
        "station_address": "示范社区 1 号",
        "skills": ("陪诊", "保洁"),
        "rating": 5.0,
        "user_active": True,
        "profile_active": True,
        "profile_present": True,
        "accepting_orders": True,
        "work_days": (1, 2, 3, 4, 5, 6, 7),
        "work_start_minute": 480,
        "work_end_minute": 1080,
        "daily_capacity": 4,
        "on_leave": False,
        "load": 0,
        "busy": (),
    }
    base.update(overrides)
    return StaffSnapshot(**base)


def _only_reason(overrides: dict) -> str:
    evaluation = evaluate(_ctx(), (_staff(**overrides),))
    assert evaluation.candidates == ()
    assert len(evaluation.excluded) == 1
    return evaluation.excluded[0].reasons[0]


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"station_id": 2}, "非本社区（站点不同）"),
        ({"user_active": False}, "账号已停用"),
        ({"profile_active": False}, "员工档案已停用"),
        ({"accepting_orders": False}, "已暂停接单"),
        ({"skills": ("保洁",)}, "技能不匹配（需陪诊）"),
        ({"work_days": (1, 3, 4)}, "当日非工作日"),
        (
            {"work_start_minute": 600},
            "超出工作时间（10:00-18:00）",
        ),
        (
            {"work_end_minute": 720},
            "超出工作时间（08:00-12:00）",
        ),
        ({"on_leave": True}, "当日请假"),
        ({"daily_capacity": 0}, "未设置每日容量"),
        ({"load": 4}, "12-01 已满（4/4）"),
    ],
)
def test_hard_filters(overrides: dict, expected: str) -> None:
    assert _only_reason(overrides) == expected


def test_cross_day_order_is_excluded() -> None:
    evaluation = evaluate(_ctx(same_day=False), (_staff(),))
    assert evaluation.excluded[0].reasons == ("跨天服务超出单日排班",)


def test_conflict_uses_left_closed_right_open_interval() -> None:
    # 订单 09:00-13:00，已有单 13:00-14:00：首尾相接不算冲突
    touching = _staff(
        busy=(TimeSlot(datetime(2026, 12, 1, 13, 0, tzinfo=TZ),
                       datetime(2026, 12, 1, 14, 0, tzinfo=TZ), "SO20261201001"),)
    )
    evaluation = evaluate(_ctx(), (touching,))
    assert len(evaluation.candidates) == 1

    # 12:00-14:00 与订单有 1 小时重叠：排除并带出冲突单号
    overlapping = _staff(
        busy=(TimeSlot(datetime(2026, 12, 1, 12, 0, tzinfo=TZ),
                       datetime(2026, 12, 1, 14, 0, tzinfo=TZ), "SO20261201002"),)
    )
    excluded = evaluate(_ctx(), (overlapping,)).excluded
    assert excluded[0].reasons == ("时间冲突（订单 SO20261201002 12-01 12:00-14:00）",)


def test_full_score_and_stable_order() -> None:
    ctx = _ctx()
    # 100 分：40 技能 + 20 可用 + 20 负载 + 10 评分 + 10 同社区
    top = _staff(staff_id=2, name="李师傅")
    # 78 分：40 + 20 + (1-2/4)*20=10 + 4.2/5*10≈8 + 不同社区 0
    lower = _staff(
        staff_id=1,
        name="王阿姨",
        rating=4.2,
        load=2,
        station_name="其他街道站",
        station_address="其他街道 1 号",
    )
    report = evaluate(ctx, (lower, top))

    assert [item.staff_id for item in report.candidates] == [2, 1]
    assert [item.score for item in report.candidates] == [100, 78]
    assert report.candidates[0].reasons[0] == "同社区"
    assert report.candidates[1].reasons[0] == "同站点，非同社区"
    assert report.excluded == ()
    assert report.data_gaps == ()


def test_risks_for_high_load_low_rating_and_missing_profile() -> None:
    staff = _staff(
        staff_id=3,
        rating=4.2,
        load=3,
        station_name="其他街道站",
        station_address="其他街道 1 号",
        profile_present=False,
    )
    candidate = evaluate(_ctx(), (staff,)).candidates[0]
    assert candidate.risks == (
        "非同社区，需跨小区出行",
        "历史评分偏低（4.2）",
        "12-01 接近满负荷",
        "未维护排班档案，按默认 08:00-18:00 计算",
    )


def test_near_capacity_is_still_candidate() -> None:
    staff = _staff(load=3, daily_capacity=4)
    candidate = evaluate(_ctx(), (staff,)).candidates[0]
    assert candidate.load == 3
    assert candidate.capacity == 4


def test_data_gaps_when_context_incomplete() -> None:
    ctx = _ctx(
        station_id=None,
        required_skill=None,
        elder_community="",
        same_day=False,
    )
    report = evaluate(ctx, (_staff(profile_present=False),))
    assert set(report.data_gaps) == {
        "该服务未配置所需技能，未做技能过滤",
        "老人未维护社区，同社区加分统一为 0",
        "本社区暂无员工档案",
        "订单为跨天服务，无法匹配单日排班，员工会全部被排除",
    }


def test_data_gap_counts_staff_without_profile() -> None:
    report = evaluate(
        _ctx(), (_staff(staff_id=1, profile_present=False), _staff(staff_id=2))
    )
    assert "1 名员工未维护排班档案，按默认 08:00-18:00 计算" in report.data_gaps
