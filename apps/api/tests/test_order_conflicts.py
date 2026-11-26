"""派单时段冲突：已有订单区间与新订单区间重叠时必须拒绝。"""

from __future__ import annotations

from datetime import datetime, time, timedelta

import pytest
from fastapi.testclient import TestClient

from app.core.time import business_tz
from app.main import app


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as test_client:
        yield test_client


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _admin(client: TestClient) -> dict:
    resp = client.post(
        "/api/v1/auth/admin/login",
        json={"username": "13900000000", "password": "Admin123!"},
    )
    assert resp.status_code == 200, resp.text
    return _headers(resp.json()["access_token"])


def _customer(client: TestClient) -> dict:
    resp = client.post(
        "/api/v1/auth/login", json={"phone": "13800000001", "password": "123456"}
    )
    assert resp.status_code == 200, resp.text
    return _headers(resp.json()["access_token"])


def _elder_and_services(client: TestClient, customer: dict) -> tuple[int, dict[str, dict]]:
    elders = client.get("/api/v1/elders", headers=customer).json()
    assert elders
    services = {item["code"]: item for item in client.get("/api/v1/services").json()}
    return elders[0]["id"], services


def _create_order(
    client: TestClient,
    *,
    customer: dict,
    admin: dict,
    elder_id: int,
    service_id: int,
    scheduled_at: datetime,
) -> dict:
    created = client.post(
        "/api/v1/orders",
        headers=customer,
        json={
            "elder_id": elder_id,
            "service_id": service_id,
            "scheduled_at": scheduled_at.isoformat(),
        },
    )
    assert created.status_code == 201, created.text
    order = created.json()
    confirmed = client.post(f"/api/v1/orders/{order['id']}/confirm", headers=admin)
    assert confirmed.status_code == 200, confirmed.text
    return order


def _staff_of_station(client: TestClient, admin: dict, station_id: int | None) -> list[dict]:
    staff = client.get("/api/v1/admin/staff", headers=admin).json()
    picked = [
        item
        for item in staff
        if item["status"] == "active" and item["station_id"] == station_id
    ]
    assert len(picked) >= 2, f"站点 {station_id} 至少需要两名在职员工才能验证换人"
    return picked


def _assign(client: TestClient, admin: dict, order_id: int, staff_id: int):
    return client.post(
        f"/api/v1/orders/{order_id}/assign",
        headers=admin,
        json={"staff_id": staff_id},
    )


def test_assign_rejects_overlapping_interval(client: TestClient) -> None:
    admin = _admin(client)
    customer = _customer(client)
    elder_id, services = _elder_and_services(client, customer)
    companion = services["companion"]  # 240 分钟
    errand = services["errand"]  # 60 分钟

    day = datetime.now(business_tz()).date() + timedelta(days=6)
    base = datetime.combine(day, time(9, 0), tzinfo=business_tz())

    first = _create_order(
        client,
        customer=customer,
        admin=admin,
        elder_id=elder_id,
        service_id=companion["id"],
        scheduled_at=base,
    )
    staff = _staff_of_station(client, admin, first["station_id"])
    staff1, staff2 = staff[0]["id"], staff[1]["id"]
    assert _assign(client, admin, first["id"], staff1).status_code == 200

    # 完全落在 09:00-13:00 内：必须拒绝
    overlapped = _create_order(
        client,
        customer=customer,
        admin=admin,
        elder_id=elder_id,
        service_id=errand["id"],
        scheduled_at=base + timedelta(hours=1),
    )
    rejected = _assign(client, admin, overlapped["id"], staff1)
    assert rejected.status_code == 409, rejected.text
    assert "已有订单" in rejected.json()["detail"]

    # 换人可派
    assert _assign(client, admin, overlapped["id"], staff2).status_code == 200

    # 首尾相接（13:00 开始）不算冲突
    touching = _create_order(
        client,
        customer=customer,
        admin=admin,
        elder_id=elder_id,
        service_id=errand["id"],
        scheduled_at=base + timedelta(hours=4),
    )
    assert _assign(client, admin, touching["id"], staff1).status_code == 200

    # 同一订单重复派给同一人不与自己冲突
    assert _assign(client, admin, first["id"], staff1).status_code == 200

    for order in (first, overlapped, touching):
        assert client.post(f"/api/v1/orders/{order['id']}/cancel", headers=customer).status_code == 200


def test_cross_midnight_order_blocks_next_day(client: TestClient) -> None:
    admin = _admin(client)
    customer = _customer(client)
    elder_id, services = _elder_and_services(client, customer)
    companion = services["companion"]  # 23:00 + 240 分钟 => 次日 03:00
    errand = services["errand"]

    day = datetime.now(business_tz()).date() + timedelta(days=7)
    late = datetime.combine(day, time(23, 0), tzinfo=business_tz())

    night = _create_order(
        client,
        customer=customer,
        admin=admin,
        elder_id=elder_id,
        service_id=companion["id"],
        scheduled_at=late,
    )
    staff = _staff_of_station(client, admin, night["station_id"])
    staff1, staff2 = staff[0]["id"], staff[1]["id"]
    assert _assign(client, admin, night["id"], staff1).status_code == 200

    # 次日 01:00 落在跨午夜区间内
    early = _create_order(
        client,
        customer=customer,
        admin=admin,
        elder_id=elder_id,
        service_id=errand["id"],
        scheduled_at=late + timedelta(hours=2),
    )
    rejected = _assign(client, admin, early["id"], staff1)
    assert rejected.status_code == 409, rejected.text
    assert _assign(client, admin, early["id"], staff2).status_code == 200

    for order in (night, early):
        assert client.post(f"/api/v1/orders/{order['id']}/cancel", headers=customer).status_code == 200
