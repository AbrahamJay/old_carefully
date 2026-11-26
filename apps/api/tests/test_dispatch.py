"""阶段三：确认 + 派单单事务与派单工作台指标。

重点验收：单事务、无半完成、重复提交安全、乐观并发、审计与通知。
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.time import business_tz
from app.db.models import Notification
from app.db.session import SessionLocal
from app.main import app

ALL_SKILLS = ["陪诊", "保洁", "代办", "适老化评估", "助餐"]


@dataclass(frozen=True)
class DispatchEnv:
    station_id: int
    other_station_id: int
    staff_a: int
    staff_b: int
    outsider: int
    elder_id: int
    services: dict[str, dict]


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as test_client:
        yield test_client


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _login(client: TestClient, path: str, payload: dict) -> dict:
    resp = client.post(path, json=payload)
    assert resp.status_code == 200, resp.text
    return _headers(resp.json()["access_token"])


def _admin(client: TestClient) -> dict:
    return _login(
        client,
        "/api/v1/auth/admin/login",
        {"username": "13900000000", "password": "Admin123!"},
    )


def _customer(client: TestClient) -> dict:
    return _login(client, "/api/v1/auth/login", {"phone": "13800000001", "password": "123456"})


@pytest.fixture(scope="module")
def env(client: TestClient) -> DispatchEnv:
    admin = _admin(client)
    customer = _customer(client)
    suffix = int(time.time_ns()) % 10**8

    def new_station(label: str) -> int:
        resp = client.post(
            "/api/v1/admin/stations",
            headers=admin,
            json={
                "name": f"派单测试站{label}{suffix}",
                "street": "派单测试街道",
                "address": f"派单测试社区{label} 1 号",
            },
        )
        assert resp.status_code == 201, resp.text
        return resp.json()["id"]

    station_id = new_station("A")
    other_station_id = new_station("B")

    def new_staff(label: str, station: int) -> int:
        suffix_digit = {"A": 1, "B": 2, "C": 3}[label]
        resp = client.post(
            "/api/v1/admin/staff",
            headers=admin,
            json={
                "name": f"派单员工{label}",
                "phone": f"139{suffix}{suffix_digit}",
                "skills": ALL_SKILLS,
                "station_id": station,
            },
        )
        assert resp.status_code == 201, resp.text
        return resp.json()["id"]

    elder = client.post(
        "/api/v1/elders",
        headers=customer,
        json={
            "name": f"派单测试长辈{suffix}",
            "phone": f"137{suffix:08d}",
            "community": "派单测试社区A",
            "address": "派单测试社区A 1 栋 101",
            "emergency_name": "测试家属",
            "emergency_phone": "13800000001",
            "station_id": station_id,
        },
    )
    assert elder.status_code == 201, elder.text

    services = {item["code"]: item for item in client.get("/api/v1/services").json()}
    yield DispatchEnv(
        station_id=station_id,
        other_station_id=other_station_id,
        staff_a=new_staff("A", station_id),
        staff_b=new_staff("B", station_id),
        outsider=new_staff("C", other_station_id),
        elder_id=elder.json()["id"],
        services=services,
    )

    for station in (station_id, other_station_id):
        client.patch(f"/api/v1/admin/stations/{station}", headers=admin, json={"active": False})


def _create_order(
    client: TestClient,
    env: DispatchEnv,
    *,
    customer: dict,
    admin: dict,
    scheduled_offset_hours: int = 0,
    confirm: bool = False,
    day_offset: int = 10,
) -> dict:
    day = datetime.now(business_tz()).date() + timedelta(days=day_offset)
    scheduled = datetime.combine(
        day, datetime.min.time(), tzinfo=business_tz()
    ).replace(hour=9) + timedelta(hours=scheduled_offset_hours)
    created = client.post(
        "/api/v1/orders",
        headers=customer,
        json={
            "elder_id": env.elder_id,
            "service_id": env.services["companion"]["id"],  # 240 分钟
            "scheduled_at": scheduled.isoformat(),
        },
    )
    assert created.status_code == 201, created.text
    order = created.json()
    if confirm:
        confirmed = client.post(f"/api/v1/orders/{order['id']}/confirm", headers=admin)
        assert confirmed.status_code == 200, confirmed.text
    return order


def _detail(client: TestClient, customer: dict, order_id: int) -> dict:
    resp = client.get(f"/api/v1/orders/{order_id}", headers=customer)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _summary(client: TestClient, admin: dict) -> dict:
    resp = client.get("/api/v1/admin/dispatch/summary", headers=admin)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _combine(
    client: TestClient,
    admin: dict,
    order_id: int,
    staff_id: int,
    expected_updated_at: str | None = None,
):
    body = {"staff_id": staff_id}
    if expected_updated_at is not None:
        body["expected_updated_at"] = expected_updated_at
    return client.post(
        f"/api/v1/admin/orders/{order_id}/confirm-and-assign", headers=admin, json=body
    )


def _cancel(client: TestClient, customer: dict, *orders: dict) -> None:
    for order in orders:
        resp = client.post(f"/api/v1/orders/{order['id']}/cancel", headers=customer)
        assert resp.status_code == 200, resp.text


def test_confirm_and_assign_is_single_transaction(
    client: TestClient, env: DispatchEnv
) -> None:
    admin = _admin(client)
    customer = _customer(client)
    before = _summary(client, admin)

    order = _create_order(client, env, customer=customer, admin=admin)
    detail = _detail(client, customer, order["id"])
    assert detail["status"] == "pending_confirm"

    resp = _combine(
        client,
        admin,
        order["id"],
        env.staff_a,
        expected_updated_at=detail["updated_at"],
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "assigned"
    assert body["staff"]["id"] == env.staff_a
    assert body["updated_at"] != detail["updated_at"]

    # 重复提交：第二次看到已是 assigned，返回 409，不重复派单
    again = _combine(client, admin, order["id"], env.staff_a)
    assert again.status_code == 409, again.text
    assert "已派单" in again.json()["detail"]

    # 审计只写一条 confirm_and_assign
    logs = client.get("/api/v1/admin/audit-logs", headers=admin).json()
    entries = [
        item
        for item in logs
        if item["action"] == "confirm_and_assign" and item["entity_id"] == order["id"]
    ]
    assert len(entries) == 1
    assert entries[0]["payload"]["staff_id"] == env.staff_a
    assert entries[0]["payload"]["from_status"] == "pending_confirm"

    # 通知：员工收到「新派单」，家属收到「已安排服务人员」
    with SessionLocal() as db:
        staff_notes = db.scalars(
            select(Notification).where(Notification.user_id == env.staff_a)
        ).all()
    assert any(note.title == "新派单" for note in staff_notes)
    customer_notes = client.get("/api/v1/notifications", headers=customer).json()
    assert any(note["title"] == "已安排服务人员" for note in customer_notes)

    after = _summary(client, admin)
    assert after["pending_confirm"] == before["pending_confirm"]
    assert after["confirmed"] == before["confirmed"]
    assert after["dispatched_today"] == before["dispatched_today"] + 1
    assert after["handled_today"] == before["handled_today"] + 1

    _cancel(client, customer, order)


def test_confirm_and_assign_rejects_stale_version_and_invalid_staff(
    client: TestClient, env: DispatchEnv
) -> None:
    admin = _admin(client)
    customer = _customer(client)
    order = _create_order(client, env, customer=customer, admin=admin)

    stale = _combine(
        client, admin, order["id"], env.staff_a, expected_updated_at="2000-01-01T00:00:00Z"
    )
    assert stale.status_code == 409, stale.text
    assert "已被其他人处理" in stale.json()["detail"]
    assert _detail(client, customer, order["id"])["status"] == "pending_confirm"

    missing = _combine(client, admin, order["id"], 999999)
    assert missing.status_code == 400, missing.text
    assert "不存在或不可用" in missing.json()["detail"]

    cross_station = _combine(client, admin, order["id"], env.outsider)
    assert cross_station.status_code == 400, cross_station.text
    assert "不属于本订单区域" in cross_station.json()["detail"]

    # 全部失败请求都不能把订单推进到已确认/已派单
    detail = _detail(client, customer, order["id"])
    assert detail["status"] == "pending_confirm"
    assert detail["staff"] is None

    _cancel(client, customer, order)


def test_confirm_and_assign_rolls_back_on_time_conflict(
    client: TestClient, env: DispatchEnv
) -> None:
    admin = _admin(client)
    customer = _customer(client)

    busy = _create_order(client, env, customer=customer, admin=admin, confirm=True)
    assigned = client.post(
        f"/api/v1/orders/{busy['id']}/assign", headers=admin, json={"staff_id": env.staff_a}
    )
    assert assigned.status_code == 200, assigned.text

    target = _create_order(
        client, env, customer=customer, admin=admin, scheduled_offset_hours=1
    )
    resp = _combine(client, admin, target["id"], env.staff_a)
    assert resp.status_code == 409, resp.text
    assert "已有订单" in resp.json()["detail"]

    # 回滚验证：目标订单仍是待确认，且没有留下派单记录
    detail = _detail(client, customer, target["id"])
    assert detail["status"] == "pending_confirm"
    assert detail["staff"] is None
    logs = client.get("/api/v1/admin/audit-logs", headers=admin).json()
    assert not any(
        item["action"] == "confirm_and_assign" and item["entity_id"] == target["id"]
        for item in logs
    )

    _cancel(client, customer, busy, target)


def test_confirm_and_assign_permissions(client: TestClient, env: DispatchEnv) -> None:
    admin = _admin(client)
    customer = _customer(client)
    staff_headers = _login(
        client, "/api/v1/auth/login", {"phone": "13800000002", "password": "123456"}
    )
    order = _create_order(client, env, customer=customer, admin=admin, day_offset=11)
    try:
        for headers in (customer, staff_headers):
            resp = _combine(client, headers, order["id"], env.staff_a)
            assert resp.status_code == 403, resp.text
            assert (
                client.get("/api/v1/admin/dispatch/summary", headers=headers).status_code
                == 403
            )
        anonymous = client.post(
            f"/api/v1/admin/orders/{order['id']}/confirm-and-assign",
            json={"staff_id": env.staff_a},
        )
        assert anonymous.status_code == 401, anonymous.text
    finally:
        _cancel(client, customer, order)


def test_dispatch_summary_tracks_confirm_then_assign(
    client: TestClient, env: DispatchEnv
) -> None:
    admin = _admin(client)
    customer = _customer(client)
    before = _summary(client, admin)

    order = _create_order(client, env, customer=customer, admin=admin, day_offset=12)
    created = _summary(client, admin)
    assert created["pending_confirm"] == before["pending_confirm"] + 1

    confirmed = client.post(f"/api/v1/orders/{order['id']}/confirm", headers=admin)
    assert confirmed.status_code == 200, confirmed.text
    partial = _summary(client, admin)
    assert partial["pending_confirm"] == before["pending_confirm"]
    assert partial["confirmed"] == before["confirmed"] + 1
    assert partial["dispatched_today"] == before["dispatched_today"]

    resp = _combine(client, admin, order["id"], env.staff_b)
    assert resp.status_code == 200, resp.text
    final = _summary(client, admin)
    assert final["confirmed"] == before["confirmed"]
    assert final["dispatched_today"] == before["dispatched_today"] + 1
    assert final["handled_today"] == before["handled_today"] + 1

    _cancel(client, customer, order)
