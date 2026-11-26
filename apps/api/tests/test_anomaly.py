"""阶段四：异常巡检扫描、幂等、自动收敛与处理动作。

验收对应《Agent数据底座概要设计》§8.4：
6 类异常全部进队列、连跑两次不重复、条件消失自动 resolved、snooze 到期重现、
处理动作有操作人和时间、多 worker 靠 advisory lock 只跑一个。
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.core.config import settings
from app.core.security import hash_password
from app.core.time import business_tz, utcnow
from app.db.models import Order, OrderAssignment, ServiceRecord, User
from app.db.session import SessionLocal, engine
from app.main import app
from app.modules.tasks.service import ANOMALY_LOCK_KEY

ALL_SKILLS = ["陪诊", "保洁", "代办", "适老化评估", "助餐"]


@dataclass(frozen=True)
class AnomalyEnv:
    station_id: int
    staff_id: int
    staff_headers: dict
    customer: dict
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


@pytest.fixture(scope="module")
def env(client: TestClient) -> AnomalyEnv:
    admin = _admin(client)
    suffix = int(time.time_ns()) % 10**8

    station = client.post(
        "/api/v1/admin/stations",
        headers=admin,
        json={
            "name": f"巡检测试站{suffix}",
            "street": "巡检测试街道",
            "address": "巡检测试社区 1 号",
        },
    )
    assert station.status_code == 201, station.text
    station_id = station.json()["id"]

    phone = f"139{suffix}9"
    created = client.post(
        "/api/v1/admin/staff",
        headers=admin,
        json={
            "name": f"巡检员工{suffix}",
            "phone": phone,
            "skills": ALL_SKILLS,
            "station_id": station_id,
        },
    )
    assert created.status_code == 201, created.text
    staff_id = created.json()["id"]

    # 后台建员工不带密码，这里给测试账号补一个，便于走接单/开始服务/完成流程
    # 客户账号也自建：复用种子客户会把它名下的老人顶到列表首位，污染 test_api
    customer_phone = f"136{suffix:08d}"
    with SessionLocal() as db:
        staff = db.get(User, staff_id)
        staff.password_hash = hash_password("123456")
        db.add(
            User(
                phone=customer_phone,
                name=f"巡检客户{suffix}",
                role="customer",
                password_hash=hash_password("123456"),
            )
        )
        db.commit()
    staff_headers = _login(
        client, "/api/v1/auth/login", {"phone": phone, "password": "123456"}
    )
    customer = _login(
        client, "/api/v1/auth/login", {"phone": customer_phone, "password": "123456"}
    )

    elder = client.post(
        "/api/v1/elders",
        headers=customer,
        json={
            "name": f"巡检长辈{suffix}",
            "phone": f"137{suffix:08d}",
            "community": "巡检测试社区",
            "address": "巡检测试社区 1 栋 101",
            "emergency_name": "测试家属",
            "emergency_phone": "13800000002",
            "station_id": station_id,
        },
    )
    assert elder.status_code == 201, elder.text

    services = {item["code"]: item for item in client.get("/api/v1/services").json()}
    yield AnomalyEnv(
        station_id=station_id,
        staff_id=staff_id,
        staff_headers=staff_headers,
        customer=customer,
        elder_id=elder.json()["id"],
        services=services,
    )

    client.patch(f"/api/v1/admin/stations/{station_id}", headers=admin, json={"active": False})


# --------------------------------------------------------------------- 流程
def _create_order(
    client: TestClient,
    env: AnomalyEnv,
    customer: dict,
    *,
    day_offset: int,
) -> dict:
    day = datetime.now(business_tz()).date() + timedelta(days=day_offset)
    scheduled = datetime.combine(day, datetime.min.time(), tzinfo=business_tz()).replace(hour=9)
    resp = client.post(
        "/api/v1/orders",
        headers=customer,
        json={
            "elder_id": env.elder_id,
            "service_id": env.services["companion"]["id"],  # 240 分钟
            "scheduled_at": scheduled.isoformat(),
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _confirm(client: TestClient, admin: dict, order_id: int) -> None:
    resp = client.post(f"/api/v1/orders/{order_id}/confirm", headers=admin)
    assert resp.status_code == 200, resp.text


def _assign(client: TestClient, admin: dict, env: AnomalyEnv, order_id: int) -> None:
    resp = client.post(
        f"/api/v1/orders/{order_id}/assign", headers=admin, json={"staff_id": env.staff_id}
    )
    assert resp.status_code == 200, resp.text


def _accept(client: TestClient, env: AnomalyEnv, order_id: int) -> None:
    resp = client.post(f"/api/v1/orders/{order_id}/accept", headers=env.staff_headers)
    assert resp.status_code == 200, resp.text


def _pay(client: TestClient, customer: dict, order_id: int) -> None:
    resp = client.post(f"/api/v1/orders/{order_id}/pay", headers=customer)
    assert resp.status_code == 200, resp.text


def _start(client: TestClient, env: AnomalyEnv, order_id: int) -> None:
    resp = client.post(f"/api/v1/orders/{order_id}/start", headers=env.staff_headers)
    assert resp.status_code == 200, resp.text


def _record(client: TestClient, env: AnomalyEnv, order_id: int) -> None:
    resp = client.post(
        f"/api/v1/orders/{order_id}/records",
        headers=env.staff_headers,
        json={"content": "巡检测试记录：陪同就诊并确认用药提醒。"},
    )
    assert resp.status_code == 201, resp.text


def _complete(client: TestClient, env: AnomalyEnv, order_id: int) -> None:
    resp = client.post(f"/api/v1/orders/{order_id}/complete", headers=env.staff_headers)
    assert resp.status_code == 200, resp.text


def _cancel(client: TestClient, customer: dict, order_id: int) -> None:
    resp = client.post(f"/api/v1/orders/{order_id}/cancel", headers=customer)
    assert resp.status_code == 200, resp.text


def _set_status_changed(order_id: int, value: datetime) -> None:
    with SessionLocal() as db:
        order = db.get(Order, order_id)
        order.status_changed_at = value
        db.commit()


def _set_assigned_at(order_id: int, value: datetime) -> None:
    with SessionLocal() as db:
        assignment = db.scalars(
            select(OrderAssignment).where(
                OrderAssignment.order_id == order_id,
                OrderAssignment.status == "assigned",
            )
        ).first()
        assert assignment is not None
        assignment.assigned_at = value
        db.commit()


def _set_scheduled_at(order_id: int, value: datetime) -> None:
    with SessionLocal() as db:
        order = db.get(Order, order_id)
        order.scheduled_at = value
        db.commit()


def _delete_records(order_id: int) -> None:
    with SessionLocal() as db:
        db.execute(delete(ServiceRecord).where(ServiceRecord.order_id == order_id))
        db.commit()


def _scan(client: TestClient, admin: dict) -> dict:
    resp = client.post("/api/v1/admin/tasks/scan", headers=admin)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _open_tasks(client: TestClient, admin: dict) -> list[dict]:
    resp = client.get("/api/v1/admin/tasks?status=open&page_size=200", headers=admin)
    assert resp.status_code == 200, resp.text
    return resp.json()["items"]


def _task_for(client: TestClient, admin: dict, order_id: int, task_type: str) -> dict:
    matches = [
        item
        for item in _open_tasks(client, admin)
        if item["order_id"] == order_id and item["type"] == task_type
    ]
    assert len(matches) == 1, f"订单 {order_id} 的 {task_type} 任务数不为 1：{len(matches)}"
    return matches[0]


# --------------------------------------------------------------------- 用例
def test_scan_detects_six_types_and_is_idempotent(
    client: TestClient, env: AnomalyEnv
) -> None:
    admin = _admin(client)
    customer = env.customer

    orders = {
        "pending": _create_order(client, env, customer, day_offset=20),
        "confirmed": _create_order(client, env, customer, day_offset=21),
        "assigned": _create_order(client, env, customer, day_offset=22),
        "in_service": _create_order(client, env, customer, day_offset=23),
        "balance": _create_order(client, env, customer, day_offset=24),
        "missing": _create_order(client, env, customer, day_offset=25),
    }
    ids = {label: order["id"] for label, order in orders.items()}

    now = utcnow()
    # 1) 待确认超时（120 分钟）
    _set_status_changed(ids["pending"], now - timedelta(minutes=121))

    # 2) 已确认未派单（60 分钟）
    _confirm(client, admin, ids["confirmed"])
    _set_status_changed(ids["confirmed"], now - timedelta(minutes=61))

    # 3) 已派未接单（30 分钟）
    _confirm(client, admin, ids["assigned"])
    _assign(client, admin, env, ids["assigned"])
    _set_assigned_at(ids["assigned"], now - timedelta(minutes=31))

    # 4) 服务中超时：预约时间改到「已过服务时长 + 60 分钟」
    _confirm(client, admin, ids["in_service"])
    _assign(client, admin, env, ids["in_service"])
    _accept(client, env, ids["in_service"])
    _pay(client, customer, ids["in_service"])
    _start(client, env, ids["in_service"])
    _set_scheduled_at(ids["in_service"], now - timedelta(minutes=240 + 61))

    # 5) 尾款未结：已完成、只付了定金、完成超过 24 小时
    _confirm(client, admin, ids["balance"])
    _assign(client, admin, env, ids["balance"])
    _accept(client, env, ids["balance"])
    _pay(client, customer, ids["balance"])
    _start(client, env, ids["balance"])
    _record(client, env, ids["balance"])
    _complete(client, env, ids["balance"])
    _set_status_changed(ids["balance"], now - timedelta(hours=25))

    # 6) 缺服务记录：完成后把记录删掉，模拟员工漏交
    _confirm(client, admin, ids["missing"])
    _assign(client, admin, env, ids["missing"])
    _accept(client, env, ids["missing"])
    _pay(client, customer, ids["missing"])
    _start(client, env, ids["missing"])
    _record(client, env, ids["missing"])
    _complete(client, env, ids["missing"])
    _delete_records(ids["missing"])

    first = _scan(client, admin)
    assert first["scanned"] is True
    assert first["detected"] >= 6

    expected = {
        ids["pending"]: "pending_timeout",
        ids["confirmed"]: "confirmed_unassigned",
        ids["assigned"]: "assigned_not_accepted",
        ids["in_service"]: "in_service_overrun",
        ids["balance"]: "balance_due",
        ids["missing"]: "missing_record",
    }
    tasks = [item for item in _open_tasks(client, admin) if item["order_id"] in expected]
    for order_id, task_type in expected.items():
        assert any(item["order_id"] == order_id and item["type"] == task_type for item in tasks)

    pending_task = _task_for(client, admin, ids["pending"], "pending_timeout")
    assert pending_task["severity"] == "high"
    assert pending_task["detail"]["threshold_minutes"] == 120
    assert pending_task["detail"]["facts"]["order_no"] == orders["pending"]["order_no"]
    assert "待确认" in pending_task["detail"]["why"]
    assert pending_task["detail"]["suggest"]

    balance_task = _task_for(client, admin, ids["balance"], "balance_due")
    assert balance_task["severity"] == "low"
    assert balance_task["detail"]["facts"]["remaining_cents"] > 0

    # 连跑两次：不产生重复任务
    count_before = len(tasks)
    second = _scan(client, admin)
    assert second["scanned"] is True
    assert second["created"] == 0
    tasks_after = [item for item in _open_tasks(client, admin) if item["order_id"] in expected]
    assert len(tasks_after) == count_before

    # 清尾款，避免影响同客户后续下单（已完成且欠款会挡住新订单）
    _pay(client, customer, ids["balance"])
    _pay(client, customer, ids["missing"])


def test_scan_resolves_task_when_condition_disappears(
    client: TestClient, env: AnomalyEnv
) -> None:
    admin = _admin(client)
    customer = env.customer
    order = _create_order(client, env, customer, day_offset=30)
    _set_status_changed(order["id"], utcnow() - timedelta(minutes=121))

    _scan(client, admin)
    task = _task_for(client, admin, order["id"], "pending_timeout")

    _cancel(client, customer, order["id"])
    _scan(client, admin)

    resp = client.get(f"/api/v1/admin/tasks/{task['id']}", headers=admin)
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "resolved"


def test_snooze_hides_until_expiry(client: TestClient, env: AnomalyEnv) -> None:
    admin = _admin(client)
    customer = env.customer
    order = _create_order(client, env, customer, day_offset=31)
    _set_status_changed(order["id"], utcnow() - timedelta(minutes=121))

    _scan(client, admin)
    task = _task_for(client, admin, order["id"], "pending_timeout")

    resp = client.post(
        f"/api/v1/admin/tasks/{task['id']}/snooze", headers=admin, json={"hours": 2}
    )
    assert resp.status_code == 200, resp.text
    snoozed = resp.json()
    assert snoozed["status"] == "snoozed"
    assert snoozed["snoozed_until"] is not None

    # 未到期：扫描不能把它重新打开
    _scan(client, admin)
    still = client.get(f"/api/v1/admin/tasks/{task['id']}", headers=admin).json()
    assert still["status"] == "snoozed"

    # 到期后重新出现
    with SessionLocal() as db:
        from app.db.models import AdminTask

        row = db.get(AdminTask, task["id"])
        row.snoozed_until = utcnow() - timedelta(minutes=1)
        db.commit()
    _scan(client, admin)
    reopened = client.get(f"/api/v1/admin/tasks/{task['id']}", headers=admin).json()
    assert reopened["status"] == "open"

    _cancel(client, customer, order["id"])
    _scan(client, admin)


def test_handle_and_ignore_record_actor_note_and_audit(
    client: TestClient, env: AnomalyEnv
) -> None:
    admin = _admin(client)
    customer = env.customer
    handled_order = _create_order(client, env, customer, day_offset=32)
    ignored_order = _create_order(client, env, customer, day_offset=33)
    _set_status_changed(handled_order["id"], utcnow() - timedelta(minutes=121))
    _set_status_changed(ignored_order["id"], utcnow() - timedelta(minutes=121))

    _scan(client, admin)
    handled_task = _task_for(client, admin, handled_order["id"], "pending_timeout")
    ignored_task = _task_for(client, admin, ignored_order["id"], "pending_timeout")

    resp = client.post(
        f"/api/v1/admin/tasks/{handled_task['id']}/handle",
        headers=admin,
        json={"note": "已电话联系家属，改约到明日上午"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "handled"
    assert body["note"] == "已电话联系家属，改约到明日上午"
    assert body["handled_at"] is not None
    with SessionLocal() as db:
        admin_user = db.scalars(select(User).where(User.phone == "13900000000")).first()
    assert body["handled_by"] == admin_user.id

    # 已结束的任务不能重复处理
    again = client.post(
        f"/api/v1/admin/tasks/{handled_task['id']}/handle",
        headers=admin,
        json={"note": "重复提交"},
    )
    assert again.status_code == 409, again.text

    resp = client.post(
        f"/api/v1/admin/tasks/{ignored_task['id']}/ignore",
        headers=admin,
        json={"reason": "家属已自行联系员工，无需干预"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "ignored"

    logs = client.get("/api/v1/admin/audit-logs", headers=admin).json()
    handle_logs = [
        item
        for item in logs
        if item["action"] == "task_handle" and item["entity_id"] == handled_task["id"]
    ]
    assert len(handle_logs) == 1
    assert handle_logs[0]["actor_id"] == admin_user.id
    assert handle_logs[0]["payload"]["note"] == "已电话联系家属，改约到明日上午"
    assert any(
        item["action"] == "task_ignore" and item["entity_id"] == ignored_task["id"]
        for item in logs
    )

    _cancel(client, customer, handled_order["id"])
    _cancel(client, customer, ignored_order["id"])
    _scan(client, admin)


def test_scan_is_skipped_when_advisory_lock_is_held(
    client: TestClient, env: AnomalyEnv
) -> None:
    admin = _admin(client)
    conn = engine.connect()
    try:
        got = conn.exec_driver_sql(
            "SELECT pg_try_advisory_lock(%s)", (ANOMALY_LOCK_KEY,)
        ).scalar()
        assert got is True
        resp = client.post("/api/v1/admin/tasks/scan", headers=admin)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["scanned"] is False
        assert body["skip_reason"]
    finally:
        conn.exec_driver_sql("SELECT pg_advisory_unlock(%s)", (ANOMALY_LOCK_KEY,))
        conn.close()

    # 锁释放后可以正常扫描
    assert _scan(client, admin)["scanned"] is True


def test_task_permissions_summary_and_switch(client: TestClient, env: AnomalyEnv) -> None:
    admin = _admin(client)
    customer = env.customer
    staff = env.staff_headers

    for headers in (customer, staff):
        assert client.get("/api/v1/admin/tasks", headers=headers).status_code == 403
        assert (
            client.get("/api/v1/admin/tasks/summary", headers=headers).status_code == 403
        )
        assert client.post("/api/v1/admin/tasks/scan", headers=headers).status_code == 403
    assert client.get("/api/v1/admin/tasks").status_code == 401

    summary = client.get("/api/v1/admin/tasks/summary", headers=admin).json()
    tasks = client.get("/api/v1/admin/tasks?status=open&page_size=200", headers=admin).json()
    assert summary["scan_interval_minutes"] == settings.anomaly_scan_interval_minutes
    assert summary["open"] == tasks["total"]
    assert summary["last_scan_at"] is not None
    assert summary["handled_today"] >= 1
    assert isinstance(summary["by_type"], dict)

    # 灰度开关：关闭后接口 503，前端隐藏入口
    settings.anomaly_scan_enabled = False
    try:
        resp = client.post("/api/v1/admin/tasks/scan", headers=admin)
        assert resp.status_code == 503, resp.text
        assert client.get("/api/v1/admin/tasks/summary", headers=admin).json()[
            "scan_enabled"
        ] is False
    finally:
        settings.anomaly_scan_enabled = True
