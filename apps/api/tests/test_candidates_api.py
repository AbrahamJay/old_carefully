"""阶段二：候选接口集成测试。

覆盖 8.2 验收里的关键场景：同站/技能匹配进入候选、冲突/请假/满负荷排除、
跨天 data_gaps、权限与灰度开关。

数据隔离：自建站点 + 两名员工 + 一位老人，不依赖 seed 数据。
其他用例会迁移员工/老人、停用站点，直接复用 seed 会让断言随执行顺序漂移。
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from datetime import time as dt_time

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.time import business_tz
from app.main import app

DEFAULT_CAPACITY = 4
ALL_SKILLS = ["陪诊", "保洁", "代办", "适老化评估", "助餐"]


@dataclass(frozen=True)
class CandidateEnv:
    station_id: int
    staff_a: int
    staff_b: int
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


def _staff_login(client: TestClient, phone: str) -> dict:
    return _login(client, "/api/v1/auth/login", {"phone": phone, "password": "123456"})


@pytest.fixture(scope="module")
def env(client: TestClient) -> CandidateEnv:
    admin = _admin(client)
    customer = _customer(client)
    suffix = int(time.time() * 1000) % 10**7

    station = client.post(
        "/api/v1/admin/stations",
        headers=admin,
        json={
            "name": f"候选测试站{suffix}",
            "street": "候选测试街道",
            "address": "候选测试社区 1 号",
        },
    )
    assert station.status_code == 201, station.text
    station_id = station.json()["id"]

    staff_ids: list[int] = []
    phones: list[str] = []
    for label, offset in (("A", 0), ("B", 1)):
        phone = f"139{suffix + offset:08d}"
        created = client.post(
            "/api/v1/admin/staff",
            headers=admin,
            json={
                "name": f"候选员工{label}",
                "phone": phone,
                "skills": ALL_SKILLS,
                "station_id": station_id,
            },
        )
        assert created.status_code == 201, created.text
        staff_ids.append(created.json()["id"])
        phones.append(phone)

    elder = client.post(
        "/api/v1/elders",
        headers=customer,
        json={
            "name": f"候选测试长辈{suffix}",
            "phone": f"137{suffix:08d}",
            "community": "候选测试社区",
            "address": "候选测试社区 1 栋 101",
            "emergency_name": "测试家属",
            "emergency_phone": "13800000001",
            "station_id": station_id,
        },
    )
    assert elder.status_code == 201, elder.text

    services = {item["code"]: item for item in client.get("/api/v1/services").json()}
    yield CandidateEnv(
        station_id=station_id,
        staff_a=staff_ids[0],
        staff_b=staff_ids[1],
        elder_id=elder.json()["id"],
        services=services,
    )

    # 测试库跑完即删；这里只把站点停用，避免影响同进程里后续用例的站点列表
    client.patch(
        f"/api/v1/admin/stations/{station_id}", headers=admin, json={"active": False}
    )


def _create_order(
    client: TestClient,
    *,
    customer: dict,
    admin: dict,
    env: CandidateEnv,
    service_code: str,
    scheduled_at: datetime,
    confirm: bool = True,
) -> dict:
    created = client.post(
        "/api/v1/orders",
        headers=customer,
        json={
            "elder_id": env.elder_id,
            "service_id": env.services[service_code]["id"],
            "scheduled_at": scheduled_at.isoformat(),
        },
    )
    assert created.status_code == 201, created.text
    order = created.json()
    if confirm:
        confirmed = client.post(f"/api/v1/orders/{order['id']}/confirm", headers=admin)
        assert confirmed.status_code == 200, confirmed.text
    return order


def _candidates(client: TestClient, admin: dict, order_id: int) -> dict:
    resp = client.get(f"/api/v1/admin/orders/{order_id}/candidates", headers=admin)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _assign(client: TestClient, admin: dict, order_id: int, staff_id: int):
    return client.post(
        f"/api/v1/orders/{order_id}/assign",
        headers=admin,
        json={"staff_id": staff_id},
    )


def _cancel(client: TestClient, customer: dict, *orders: dict | None) -> None:
    for order in orders:
        if order is None:
            continue
        resp = client.post(f"/api/v1/orders/{order['id']}/cancel", headers=customer)
        assert resp.status_code == 200, resp.text


def _workday(offset: int, hour: int, minute: int = 0) -> datetime:
    day = datetime.now(business_tz()).date() + timedelta(days=offset)
    return datetime.combine(day, dt_time(hour, minute), tzinfo=business_tz())


def test_candidates_rank_all_eligible_staff(
    client: TestClient, env: CandidateEnv
) -> None:
    admin = _admin(client)
    customer = _customer(client)

    # 待确认状态就应该能看候选，不必先确认
    order = _create_order(
        client,
        customer=customer,
        admin=admin,
        env=env,
        service_code="companion",  # 240 分钟，需「陪诊」技能
        scheduled_at=_workday(6, 9),
        confirm=False,
    )
    try:
        body = _candidates(client, admin, order["id"])
        assert body["required_skill"] == "陪诊"
        assert body["data_gaps"] == []

        # 本站在职员工全部进入候选；跨站员工只出现在 excluded
        assert {item["staff_id"] for item in body["candidates"]} == {
            env.staff_a,
            env.staff_b,
        }
        ids = [item["staff_id"] for item in body["candidates"]]
        # 同分按 staff_id 升序，推荐人取第一位
        assert ids == sorted(ids)
        top = body["candidates"][0]
        assert body["recommendation"] == {
            "staff_id": top["staff_id"],
            "name": top["name"],
            "score": 100,
        }
        assert top["score"] == 100
        assert top["reasons"][0] == "同社区"
        assert top["load"] == 0
        assert top["capacity"] == DEFAULT_CAPACITY
        assert top["risks"] == []
    finally:
        _cancel(client, customer, order)


def test_candidates_exclude_conflict_leave_and_full_day(
    client: TestClient, env: CandidateEnv
) -> None:
    admin = _admin(client)
    customer = _customer(client)

    busy_order = _create_order(
        client,
        customer=customer,
        admin=admin,
        env=env,
        service_code="companion",
        scheduled_at=_workday(7, 9),
    )
    target = _create_order(
        client,
        customer=customer,
        admin=admin,
        env=env,
        service_code="companion",
        scheduled_at=_workday(7, 10),  # 10:00-14:00，与 09:00-13:00 重叠
    )
    full_day = None
    try:
        assert _assign(client, admin, busy_order["id"], env.staff_a).status_code == 200

        # 1) 时间冲突：只排除被占用的员工
        body = _candidates(client, admin, target["id"])
        excluded = {item["staff_id"]: item["reasons"][0] for item in body["excluded"]}
        assert excluded[env.staff_a].startswith("时间冲突")
        assert [item["staff_id"] for item in body["candidates"]] == [env.staff_b]

        # 2) 请假：另一名可用员工也被排除后，候选为空
        day = datetime.now(business_tz()).date() + timedelta(days=7)
        leave = client.post(
            f"/api/v1/admin/staff/{env.staff_b}/leaves",
            headers=admin,
            json={"start_date": day.isoformat(), "reason": "候选测试"},
        )
        assert leave.status_code == 201, leave.text
        try:
            body = _candidates(client, admin, target["id"])
            assert body["candidates"] == []
            assert body["recommendation"] is None
            assert {item["staff_id"]: item["reasons"][0] for item in body["excluded"]}[
                env.staff_b
            ] == "当日请假"
        finally:
            deleted = client.delete(
                f"/api/v1/admin/staff/{env.staff_b}/leaves",
                headers=admin,
                params={"from_date": day.isoformat()},
            )
            assert deleted.status_code == 200, deleted.text

        # 3) 满负荷：容量调到 1 并占用后，该员工被排除
        assert _assign(client, admin, target["id"], env.staff_b).status_code == 200
        patched = client.patch(
            f"/api/v1/admin/staff/{env.staff_b}",
            headers=admin,
            json={"daily_capacity": 1},
        )
        assert patched.status_code == 200, patched.text
        full_day = _create_order(
            client,
            customer=customer,
            admin=admin,
            env=env,
            service_code="renovation",
            scheduled_at=_workday(7, 14),  # 14:00-15:30，与已有单首尾相接
        )
        body = _candidates(client, admin, full_day["id"])
        excluded = {item["staff_id"]: item["reasons"][0] for item in body["excluded"]}
        assert excluded[env.staff_b] == f"{_workday(7, 14).strftime('%m-%d')} 已满（1/1）"
        # 另一名员工 14:00 与 09:00-13:00 首尾相接，仍可候选
        assert env.staff_a in {item["staff_id"] for item in body["candidates"]}
    finally:
        restored = client.patch(
            f"/api/v1/admin/staff/{env.staff_b}",
            headers=admin,
            json={"daily_capacity": DEFAULT_CAPACITY},
        )
        assert restored.status_code == 200, restored.text
        _cancel(client, customer, busy_order, target, full_day)


def test_cross_day_order_reports_data_gap(
    client: TestClient, env: CandidateEnv
) -> None:
    admin = _admin(client)
    customer = _customer(client)

    order = _create_order(
        client,
        customer=customer,
        admin=admin,
        env=env,
        service_code="companion",  # 23:00 + 240 分钟 = 次日 03:00
        scheduled_at=_workday(8, 23),
        confirm=False,
    )
    try:
        body = _candidates(client, admin, order["id"])
        assert body["candidates"] == []
        assert body["recommendation"] is None
        assert "订单为跨天服务，无法匹配单日排班，员工会全部被排除" in body["data_gaps"]
        excluded = {item["staff_id"]: item["reasons"][0] for item in body["excluded"]}
        assert {excluded[env.staff_a], excluded[env.staff_b]} == {"跨天服务超出单日排班"}
    finally:
        _cancel(client, customer, order)


def test_candidates_permission_and_feature_flag(
    client: TestClient, env: CandidateEnv, monkeypatch
) -> None:
    admin = _admin(client)
    customer = _customer(client)

    order = _create_order(
        client,
        customer=customer,
        admin=admin,
        env=env,
        service_code="companion",
        scheduled_at=_workday(9, 9),
        confirm=False,
    )
    try:
        # 只有管理员能看候选
        staff_headers = _staff_login(client, "13800000002")
        for headers in (customer, staff_headers):
            resp = client.get(
                f"/api/v1/admin/orders/{order['id']}/candidates", headers=headers
            )
            assert resp.status_code == 403, resp.text

        assert (
            client.get("/api/v1/admin/orders/999999/candidates", headers=admin).status_code
            == 404
        )

        # 灰度开关关闭：返回 503，前端据此隐藏建议卡
        monkeypatch.setattr(settings, "candidate_ranking_enabled", False)
        off = client.get(f"/api/v1/admin/orders/{order['id']}/candidates", headers=admin)
        assert off.status_code == 503, off.text
        assert off.json()["code"] == "unavailable"

        monkeypatch.setattr(settings, "candidate_ranking_enabled", True)
        assert (
            client.get(f"/api/v1/admin/orders/{order['id']}/candidates", headers=admin)
        ).status_code == 200
    finally:
        _cancel(client, customer, order)
