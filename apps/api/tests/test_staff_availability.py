"""阶段一：员工可用性、请假、服务技能与订单状态时间。"""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from app.db.models import Order
from app.db.session import SessionLocal
from app.main import app

DEFAULTS = {
    "work_days": [1, 2, 3, 4, 5, 6, 7],
    "work_start_minute": 480,
    "work_end_minute": 1080,
    "daily_capacity": 4,
    "accepting_orders": True,
}


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as test_client:
        yield test_client


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _admin_headers(client: TestClient) -> dict:
    resp = client.post(
        "/api/v1/auth/admin/login",
        json={"username": "13900000000", "password": "Admin123!"},
    )
    assert resp.status_code == 200, resp.text
    return _headers(resp.json()["access_token"])


def _staff_headers(client: TestClient) -> dict:
    resp = client.post(
        "/api/v1/auth/login", json={"phone": "13800000002", "password": "123456"}
    )
    assert resp.status_code == 200, resp.text
    return _headers(resp.json()["access_token"])


def _customer_headers(client: TestClient) -> dict:
    resp = client.post(
        "/api/v1/auth/login", json={"phone": "13800000001", "password": "123456"}
    )
    assert resp.status_code == 200, resp.text
    return _headers(resp.json()["access_token"])


def _first_staff_id(client: TestClient, admin: dict) -> int:
    staff = client.get("/api/v1/admin/staff", headers=admin).json()
    assert staff
    return staff[0]["id"]


def test_staff_availability_defaults_and_update(client: TestClient) -> None:
    admin = _admin_headers(client)
    staff = client.get("/api/v1/admin/staff", headers=admin).json()
    assert staff
    first = staff[0]
    for key, expected in DEFAULTS.items():
        assert first[key] == expected, (key, first[key])
    assert isinstance(first["today_load"], int)
    staff_id = first["id"]

    update = {
        "work_days": [5, 1, 3, 3],
        "work_start_minute": 540,
        "work_end_minute": 1020,
        "daily_capacity": 2,
        "accepting_orders": False,
    }
    resp = client.patch(f"/api/v1/admin/staff/{staff_id}", headers=admin, json=update)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["work_days"] == [1, 3, 5]  # 去重并排序
    assert body["work_start_minute"] == 540
    assert body["work_end_minute"] == 1020
    assert body["daily_capacity"] == 2
    assert body["accepting_orders"] is False

    # 非法工作日与非法时段都要被拒绝
    bad_days = client.patch(
        f"/api/v1/admin/staff/{staff_id}", headers=admin, json={"work_days": [0, 8]}
    )
    assert bad_days.status_code == 422, bad_days.text
    bad_range = client.patch(
        f"/api/v1/admin/staff/{staff_id}",
        headers=admin,
        json={"work_start_minute": 1080, "work_end_minute": 480},
    )
    assert bad_range.status_code == 400, bad_range.text

    restore = client.patch(f"/api/v1/admin/staff/{staff_id}", headers=admin, json=DEFAULTS)
    assert restore.status_code == 200, restore.text


def test_staff_leaves_range_and_idempotency(client: TestClient) -> None:
    admin = _admin_headers(client)
    staff_id = _first_staff_id(client, admin)

    created = client.post(
        f"/api/v1/admin/staff/{staff_id}/leaves",
        headers=admin,
        json={"start_date": "2031-01-06", "end_date": "2031-01-08", "reason": "年假"},
    )
    assert created.status_code == 201, created.text
    days = [item["leave_date"] for item in created.json()]
    assert days == ["2031-01-06", "2031-01-07", "2031-01-08"]
    leave_ids = {item["id"] for item in created.json()}

    # 同一区间重复提交只改备注，不产生重复记录
    again = client.post(
        f"/api/v1/admin/staff/{staff_id}/leaves",
        headers=admin,
        json={"start_date": "2031-01-06", "end_date": "2031-01-08", "reason": "家中有事"},
    )
    assert again.status_code == 201, again.text
    assert {item["id"] for item in again.json()} == leave_ids
    assert {item["reason"] for item in again.json()} == {"家中有事"}

    # 只传开始日期等同只请一天；与既有区间重叠时并入
    one_day = client.post(
        f"/api/v1/admin/staff/{staff_id}/leaves",
        headers=admin,
        json={"start_date": "2031-01-07", "reason": "调休"},
    )
    assert one_day.status_code == 201, one_day.text
    assert len(one_day.json()) == 1
    assert one_day.json()[0]["id"] in leave_ids

    listed = client.get(f"/api/v1/admin/staff/{staff_id}/leaves", headers=admin)
    assert listed.status_code == 200, listed.text
    assert len(listed.json()) == 3

    # 非法区间与超长区间直接拒绝
    reversed_range = client.post(
        f"/api/v1/admin/staff/{staff_id}/leaves",
        headers=admin,
        json={"start_date": "2031-02-10", "end_date": "2031-02-01"},
    )
    assert reversed_range.status_code == 422, reversed_range.text
    too_long = client.post(
        f"/api/v1/admin/staff/{staff_id}/leaves",
        headers=admin,
        json={"start_date": "2031-01-01", "end_date": "2032-06-01"},
    )
    assert too_long.status_code == 422, too_long.text

    deleted = client.delete(
        f"/api/v1/admin/staff/{staff_id}/leaves",
        headers=admin,
        params={"from_date": "2031-01-06", "to_date": "2031-01-08"},
    )
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["deleted"] == 3
    assert client.get(f"/api/v1/admin/staff/{staff_id}/leaves", headers=admin).json() == []

    # 单条删除接口保留，用于按记录删除
    single = client.post(
        f"/api/v1/admin/staff/{staff_id}/leaves",
        headers=admin,
        json={"start_date": "2031-01-09", "reason": "事假"},
    )
    assert single.status_code == 201, single.text
    leave_id = single.json()[0]["id"]
    assert (
        client.delete(
            f"/api/v1/admin/staff/{staff_id}/leaves/{leave_id}", headers=admin
        ).status_code
        == 204
    )
    missing = client.delete(
        f"/api/v1/admin/staff/{staff_id}/leaves/{leave_id}", headers=admin
    )
    assert missing.status_code == 404, missing.text

    # 非员工不能挂请假
    not_staff = client.post(
        "/api/v1/admin/staff/999999/leaves",
        headers=admin,
        json={"start_date": "2031-01-06"},
    )
    assert not_staff.status_code == 404, not_staff.text


def test_staff_on_leave_today_badge(client: TestClient) -> None:
    admin = _admin_headers(client)
    staff_id = _first_staff_id(client, admin)
    today = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()

    created = client.post(
        f"/api/v1/admin/staff/{staff_id}/leaves",
        headers=admin,
        json={"start_date": today, "reason": "今日请假"},
    )
    assert created.status_code == 201, created.text
    try:
        staff = client.get("/api/v1/admin/staff", headers=admin).json()
        assert next(item for item in staff if item["id"] == staff_id)["on_leave_today"] is True
        assert all(
            item["on_leave_today"] is False for item in staff if item["id"] != staff_id
        )
    finally:
        client.delete(
            f"/api/v1/admin/staff/{staff_id}/leaves",
            headers=admin,
            params={"from_date": today},
        )

    # 删除后徽标自动消失，不依赖任何状态字段
    staff = client.get("/api/v1/admin/staff", headers=admin).json()
    assert next(item for item in staff if item["id"] == staff_id)["on_leave_today"] is False


def test_service_required_skill_exposed(client: TestClient) -> None:
    services = client.get("/api/v1/services").json()
    by_code = {item["code"]: item for item in services}
    assert by_code["companion"]["required_skill"] == "陪诊"
    assert by_code["cleaning"]["required_skill"] == "保洁"


def test_order_status_changed_at_only_moves_on_status_change(client: TestClient) -> None:
    admin = _admin_headers(client)
    customer = _customer_headers(client)

    elders = client.get("/api/v1/elders", headers=customer).json()
    services = client.get("/api/v1/services").json()
    scheduled = datetime.now(timezone.utc).replace(microsecond=0)
    created = client.post(
        "/api/v1/orders",
        headers=customer,
        json={
            "elder_id": elders[0]["id"],
            "service_id": services[0]["id"],
            "scheduled_at": scheduled.isoformat(),
        },
    )
    assert created.status_code == 201, created.text
    order_id = created.json()["id"]

    def read_times() -> tuple[datetime, datetime]:
        with SessionLocal() as db:
            order = db.get(Order, order_id)
            assert order is not None
            return order.status_changed_at, order.updated_at

    t0, _ = read_times()
    assert abs((datetime.now(timezone.utc) - t0).total_seconds()) < 30

    confirmed = client.post(f"/api/v1/orders/{order_id}/confirm", headers=admin)
    assert confirmed.status_code == 200, confirmed.text
    t1, _ = read_times()
    assert t1 >= t0

    # 仅改备注：updated_at 刷新，status_changed_at 保持不变
    with SessionLocal() as db:
        order = db.get(Order, order_id)
        assert order is not None
        order.notes = "家属补充：门口有台阶"
        db.commit()
    t2, updated_at = read_times()
    assert t2 == t1
    assert updated_at > t1

    cancelled = client.post(f"/api/v1/orders/{order_id}/cancel", headers=customer)
    assert cancelled.status_code == 200, cancelled.text
    t3, _ = read_times()
    assert t3 >= t2
