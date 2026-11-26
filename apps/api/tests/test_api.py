from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

# 测试库准备（独立库、清 schema、注入环境变量）在 tests/conftest.py 里，导入 app 前已完成
from app.main import app


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as test_client:
        yield test_client


def _token(client: TestClient, phone: str) -> str:
    resp = client.post(
        "/api/v1/auth/login",
        json={"phone": phone, "password": "123456"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _admin_token(client: TestClient) -> str:
    resp = client.post(
        "/api/v1/auth/admin/login",
        json={"username": "13900000000", "password": "Admin123!"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_health(client: TestClient) -> None:
    assert client.get("/healthz").json()["ok"] is True


def test_login_rejects_unknown_phone(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/auth/login",
        json={"phone": "13800000099", "password": "123456"},
    )
    assert resp.status_code == 401, resp.text
    assert "手机号或密码错误" in resp.json()["detail"]


def test_login_with_password(client: TestClient) -> None:
    """手机号 + 密码是唯一登录方式，初始密码 123456。"""
    ok = client.post("/api/v1/auth/login", json={"phone": "13800000001", "password": "123456"})
    assert ok.status_code == 200, ok.text
    assert client.get("/api/v1/elders", headers=_headers(ok.json()["access_token"])).status_code == 200

    bad = client.post("/api/v1/auth/login", json={"phone": "13800000001", "password": "wrong123"})
    assert bad.status_code == 401

    # 旧验证码字段不再接受
    code_only = client.post(
        "/api/v1/auth/login", json={"phone": "13800000001", "code": "123456"}
    )
    assert code_only.status_code == 422
    both = client.post(
        "/api/v1/auth/login", json={"phone": "13800000001", "password": "123456", "code": "123456"}
    )
    assert both.status_code == 422
    neither = client.post("/api/v1/auth/login", json={"phone": "13800000001"})
    assert neither.status_code == 422


def test_order_lifecycle(client: TestClient) -> None:
    customer = _token(client, "13800000001")
    admin = _admin_token(client)
    staff = _token(client, "13800000002")

    elders = client.get("/api/v1/elders", headers=_headers(customer)).json()
    services = client.get("/api/v1/services").json()
    assert elders and services

    scheduled = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    create = client.post(
        "/api/v1/orders",
        headers=_headers(customer),
        json={
            "elder_id": elders[0]["id"],
            "service_id": services[0]["id"],
            "scheduled_at": scheduled,
            "address": elders[0]["address"],
            "contact_name": "张女士",
            "contact_phone": "13800000001",
            "notes": "pytest 全链路",
        },
    )
    assert create.status_code == 201, create.text
    order_id = create.json()["id"]
    assert create.json()["status"] == "pending_confirm"
    assert create.json()["deposit_cents"] > 0

    confirm = client.post(f"/api/v1/orders/{order_id}/confirm", headers=_headers(admin))
    assert confirm.status_code == 200, confirm.text
    assert confirm.json()["status"] == "confirmed"

    staff_list = client.get("/api/v1/admin/staff", headers=_headers(admin)).json()
    assert staff_list

    assign = client.post(
        f"/api/v1/orders/{order_id}/assign",
        headers=_headers(admin),
        json={"staff_id": staff_list[0]["id"]},
    )
    assert assign.status_code == 200, assign.text
    assert assign.json()["status"] == "assigned"

    pay_deposit = client.post(f"/api/v1/orders/{order_id}/pay", headers=_headers(customer))
    assert pay_deposit.status_code == 200, pay_deposit.text
    assert pay_deposit.json()["payment_status"] == "deposit_paid"
    assert pay_deposit.json()["paid_cents"] == pay_deposit.json()["deposit_cents"]

    accept = client.post(f"/api/v1/orders/{order_id}/accept", headers=_headers(staff))
    assert accept.status_code == 200, accept.text

    start = client.post(f"/api/v1/orders/{order_id}/start", headers=_headers(staff))
    assert start.status_code == 200, start.text
    assert start.json()["status"] == "in_service"

    record = client.post(
        f"/api/v1/orders/{order_id}/records",
        headers=_headers(staff),
        json={
            "content": "已陪同完成复查，医嘱已拍照发给家属。",
            "photos": [],
            "elder_confirmed": True,
        },
    )
    assert record.status_code == 201, record.text
    assert record.json()["elder_confirmed"] is False

    complete = client.post(f"/api/v1/orders/{order_id}/complete", headers=_headers(staff))
    assert complete.status_code == 200, complete.text
    assert complete.json()["status"] == "completed"
    assert len(complete.json()["records"]) == 1

    confirm_service = client.post(
        f"/api/v1/orders/{order_id}/confirm-service", headers=_headers(customer)
    )
    assert confirm_service.status_code == 200, confirm_service.text
    assert confirm_service.json()["records"][0]["elder_confirmed"] is True

    review = client.post(
        f"/api/v1/orders/{order_id}/review",
        headers=_headers(customer),
        json={"rating": 5, "content": "服务很细。"},
    )
    assert review.status_code == 201, review.text

    pay = client.post(
        f"/api/v1/orders/{order_id}/pay-offline",
        headers=_headers(admin),
        json={"method": "wechat_transfer"},
    )
    assert pay.status_code == 200, pay.text
    assert pay.json()["payment_status"] == "paid_offline"
    assert pay.json()["remaining_cents"] == 0

    refund = client.post(f"/api/v1/orders/{order_id}/refund", headers=_headers(admin))
    assert refund.status_code == 200, refund.text
    assert refund.json()["payment_status"] == "refunded"
    assert refund.json()["refunded_cents"] > 0

    detail = client.get(f"/api/v1/orders/{order_id}", headers=_headers(customer)).json()
    assert detail["review"]["rating"] == 5
    assert detail["payment_status"] == "refunded"


def test_rbac_and_state_guard(client: TestClient) -> None:
    customer = _token(client, "13800000001")
    admin = _admin_token(client)
    elders = client.get("/api/v1/elders", headers=_headers(customer)).json()
    services = client.get("/api/v1/services").json()

    create = client.post(
        "/api/v1/orders",
        headers=_headers(customer),
        json={
            "elder_id": elders[0]["id"],
            "service_id": services[0]["id"],
            "scheduled_at": (datetime.now(timezone.utc) + timedelta(days=2)).isoformat(),
        },
    )
    order_id = create.json()["id"]

    # 客户不能确认订单
    forbidden = client.post(f"/api/v1/orders/{order_id}/confirm", headers=_headers(customer))
    assert forbidden.status_code == 403

    # 管理员确认后不能重复确认
    first = client.post(f"/api/v1/orders/{order_id}/confirm", headers=_headers(admin))
    assert first.status_code == 200
    second = client.post(f"/api/v1/orders/{order_id}/confirm", headers=_headers(admin))
    assert second.status_code == 409

    # 管理员不能提交员工完成动作
    admin_complete = client.post(f"/api/v1/orders/{order_id}/complete", headers=_headers(admin))
    assert admin_complete.status_code == 403


def test_upload_and_file(client: TestClient) -> None:
    customer = _token(client, "13800000001")
    content = b"\xff\xd8\xff\xe0" + b"0" * 128
    resp = client.post(
        "/api/v1/uploads",
        headers=_headers(customer),
        files={"file": ("demo.jpg", content, "image/jpeg")},
    )
    assert resp.status_code == 200, resp.text
    url = resp.json()["url"]
    file_resp = client.get(url)
    assert file_resp.status_code == 200
    assert file_resp.content == content

    bad = client.post(
        "/api/v1/uploads",
        headers=_headers(customer),
        files={"file": ("demo.txt", b"hello", "text/plain")},
    )
    assert bad.status_code == 400


def test_admin_stats(client: TestClient) -> None:
    admin = _admin_token(client)
    stats = client.get("/api/v1/admin/stats", headers=_headers(admin))
    assert stats.status_code == 200
    body = stats.json()
    assert body["total_customers"] >= 2
    assert body["total_elders"] >= 3
    assert body["revenue_cents"] > 0


def test_station_filters_and_pagination(client: TestClient) -> None:
    admin = _admin_token(client)
    headers = _headers(admin)

    stations = client.get("/api/v1/admin/stations", headers=headers)
    assert stations.status_code == 200, stations.text
    station_list = stations.json()
    assert station_list
    station_id = station_list[0]["id"]

    staff = client.get(f"/api/v1/admin/staff?station_id={station_id}", headers=headers)
    assert staff.status_code == 200, staff.text
    assert staff.json()
    assert all(item["station_id"] == station_id for item in staff.json())

    elders = client.get(f"/api/v1/admin/elders?station_id={station_id}", headers=headers)
    assert elders.status_code == 200, elders.text
    assert elders.json()
    assert all(item["station_name"] for item in elders.json())

    first_page = client.get(
        f"/api/v1/admin/orders?station_id={station_id}&page=1&page_size=2",
        headers=headers,
    )
    assert first_page.status_code == 200, first_page.text
    body = first_page.json()
    assert body["page"] == 1
    assert body["page_size"] == 2
    assert len(body["items"]) <= 2
    assert body["total"] >= 1
    assert all(item["station_name"] for item in body["items"])

    keyword = client.get(
        f"/api/v1/admin/orders?station_id={station_id}&keyword=张", headers=headers
    )
    assert keyword.status_code == 200, keyword.text
    assert keyword.json()["items"]


def test_station_management(client: TestClient) -> None:
    admin = _admin_token(client)
    headers = _headers(admin)

    create = client.post(
        "/api/v1/admin/stations",
        headers=headers,
        json={
            "name": "测试片区",
            "street": "测试街道",
            "address": "测试社区 1 号",
            "active": True,
        },
    )
    assert create.status_code == 201, create.text
    station = create.json()
    assert station["name"] == "测试片区"
    assert station["active"] is True

    duplicate = client.post(
        "/api/v1/admin/stations",
        headers=headers,
        json={"name": "测试片区"},
    )
    assert duplicate.status_code == 400

    update = client.patch(
        f"/api/v1/admin/stations/{station['id']}",
        headers=headers,
        json={"name": "测试片区 A"},
    )
    assert update.status_code == 200, update.text
    assert update.json()["name"] == "测试片区 A"
    assert update.json()["active"] is True

    staff = client.post(
        "/api/v1/admin/staff",
        headers=headers,
        json={
            "name": "测试员工",
            "phone": "13800000099",
            "skills": ["保洁"],
            "station_id": station["id"],
        },
    )
    assert staff.status_code == 201, staff.text
    assert staff.json()["station_id"] == station["id"]

    elders = client.get("/api/v1/admin/elders", headers=headers).json()
    elder = elders[0]
    moved = client.patch(
        f"/api/v1/elders/{elder['id']}",
        headers=headers,
        json={"station_id": station["id"]},
    )
    assert moved.status_code == 200, moved.text
    assert moved.json()["station_id"] == station["id"]

    disabled = client.patch(
        f"/api/v1/admin/stations/{station['id']}",
        headers=headers,
        json={"active": False},
    )
    assert disabled.status_code == 200, disabled.text
    assert disabled.json()["active"] is False


def test_customer_can_choose_station_for_new_elder(client: TestClient) -> None:
    customer = _token(client, "13800000001")
    headers = _headers(customer)

    stations = client.get("/api/v1/stations", headers=headers)
    assert stations.status_code == 200, stations.text
    station_list = stations.json()
    assert station_list
    station = station_list[0]

    create = client.post(
        "/api/v1/elders",
        headers=headers,
        json={
            "name": "测试区域长辈",
            "phone": "13700000099",
            "community": "测试社区",
            "address": "测试社区 1 栋 101",
            "emergency_name": "测试家属",
            "emergency_phone": "13800000001",
            "station_id": station["id"],
        },
    )
    assert create.status_code == 201, create.text
    assert create.json()["station_id"] == station["id"]
    assert create.json()["station_name"] == station["name"]


def test_cancel_order_refunds_deposit(client: TestClient) -> None:
    customer = _token(client, "13800000001")
    headers = _headers(customer)
    elders = client.get("/api/v1/elders", headers=headers).json()
    services = client.get("/api/v1/services").json()
    create = client.post(
        "/api/v1/orders",
        headers=headers,
        json={
            "elder_id": elders[0]["id"],
            "service_id": services[0]["id"],
            "scheduled_at": (datetime.now(timezone.utc) + timedelta(days=3)).isoformat(),
        },
    )
    assert create.status_code == 201, create.text
    order = create.json()
    order_id = order["id"]

    deposit = client.post(f"/api/v1/orders/{order_id}/pay", headers=headers)
    assert deposit.status_code == 200, deposit.text
    assert deposit.json()["payment_status"] == "deposit_paid"

    cancel = client.post(f"/api/v1/orders/{order_id}/cancel", headers=headers)
    assert cancel.status_code == 200, cancel.text
    body = cancel.json()
    assert body["status"] == "cancelled"
    assert body["payment_status"] == "refunded"
    assert body["refunded_cents"] == body["paid_cents"]


def test_refund_cancels_unstarted_order_and_blocks_dispatch(client: TestClient) -> None:
    """退款即终止：未开始服务的订单退款后自动取消，不能再派单。"""
    customer = _token(client, "13800000001")
    admin = _headers(_admin_token(client))
    headers = _headers(customer)
    elders = client.get("/api/v1/elders", headers=headers).json()
    services = client.get("/api/v1/services").json()
    create = client.post(
        "/api/v1/orders",
        headers=headers,
        json={
            "elder_id": elders[0]["id"],
            "service_id": services[0]["id"],
            "scheduled_at": (datetime.now(timezone.utc) + timedelta(days=4)).isoformat(),
        },
    )
    assert create.status_code == 201, create.text
    order_id = create.json()["id"]

    confirm = client.post(f"/api/v1/orders/{order_id}/confirm", headers=admin)
    assert confirm.status_code == 200, confirm.text
    pay = client.post(f"/api/v1/orders/{order_id}/pay", headers=headers)
    assert pay.json()["payment_status"] == "deposit_paid"

    refund = client.post(f"/api/v1/orders/{order_id}/refund", headers=admin)
    assert refund.status_code == 200, refund.text
    body = refund.json()
    assert body["payment_status"] == "refunded"
    assert body["status"] == "cancelled"

    staff_id = client.get("/api/v1/admin/staff", headers=admin).json()[0]["id"]
    assign = client.post(
        f"/api/v1/orders/{order_id}/assign", headers=admin, json={"staff_id": staff_id}
    )
    assert assign.status_code == 409, assign.text

    # 历史数据兼容：绕过取消直接置成「已确认 + 已退款」时，派单/确认也必须被拒
    from app.db.models import Order
    from app.db.session import SessionLocal

    with SessionLocal() as db:
        row = db.get(Order, order_id)
        row.status = "confirmed"
        row.payment_status = "refunded"
        db.commit()

    assign = client.post(
        f"/api/v1/orders/{order_id}/assign", headers=admin, json={"staff_id": staff_id}
    )
    assert assign.status_code == 409, assign.text
    assert "已退款" in assign.json()["detail"]
    dispatch = client.post(
        f"/api/v1/admin/orders/{order_id}/confirm-and-assign",
        headers=admin,
        json={"staff_id": staff_id},
    )
    assert dispatch.status_code == 409, dispatch.text
    assert "已退款" in dispatch.json()["detail"]


def test_outstanding_balance_blocks_new_order(client: TestClient) -> None:
    customer = _token(client, "13800000001")
    admin = _admin_token(client)
    staff = _token(client, "13800000002")
    ch = _headers(customer)

    elders = client.get("/api/v1/elders", headers=ch).json()
    services = client.get("/api/v1/services").json()
    create = client.post(
        "/api/v1/orders",
        headers=ch,
        json={
            "elder_id": elders[0]["id"],
            "service_id": services[0]["id"],
            "scheduled_at": (datetime.now(timezone.utc) + timedelta(days=4)).isoformat(),
        },
    )
    assert create.status_code == 201, create.text
    order_id = create.json()["id"]

    client.post(f"/api/v1/orders/{order_id}/confirm", headers=_headers(admin))
    staff_id = client.get("/api/v1/admin/staff", headers=_headers(admin)).json()[0]["id"]
    client.post(
        f"/api/v1/orders/{order_id}/assign",
        headers=_headers(admin),
        json={"staff_id": staff_id},
    )
    client.post(f"/api/v1/orders/{order_id}/pay", headers=ch)
    client.post(f"/api/v1/orders/{order_id}/accept", headers=_headers(staff))
    client.post(f"/api/v1/orders/{order_id}/start", headers=_headers(staff))
    client.post(
        f"/api/v1/orders/{order_id}/records",
        headers=_headers(staff),
        json={"content": "测试尾款拦截", "photos": []},
    )
    client.post(f"/api/v1/orders/{order_id}/complete", headers=_headers(staff))

    blocked = client.post(
        "/api/v1/orders",
        headers=ch,
        json={
            "elder_id": elders[0]["id"],
            "service_id": services[0]["id"],
            "scheduled_at": (datetime.now(timezone.utc) + timedelta(days=5)).isoformat(),
        },
    )
    assert blocked.status_code == 409, blocked.text
    assert "尾款" in blocked.json()["detail"]

    paid = client.post(f"/api/v1/orders/{order_id}/pay", headers=ch)
    assert paid.status_code == 200, paid.text
    assert paid.json()["remaining_cents"] == 0
    assert paid.json()["service_confirmed"] is True

    allowed = client.post(
        "/api/v1/orders",
        headers=ch,
        json={
            "elder_id": elders[0]["id"],
            "service_id": services[1]["id"],
            "scheduled_at": (datetime.now(timezone.utc) + timedelta(days=6)).isoformat(),
        },
    )
    assert allowed.status_code == 201, allowed.text
