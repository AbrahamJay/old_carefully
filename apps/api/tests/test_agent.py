"""阶段五：Agent 记录代写与服务前提示。

验收对应计划中的验收路径：
开关、配额、越权、状态冲突、急症红线短路、档案为空不调模型、
审计白名单（不落原文/手机号）、网关异常映射。
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime, timedelta

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import settings
from app.core.security import hash_password
from app.core.time import business_tz
from app.db.models import AgentAction, User
from app.db.session import SessionLocal
from app.main import app
from app.modules.agents import models as agent_models
from app.modules.agents import policies
from app.modules.agents.errors import AgentRateLimitedError, AgentUnavailableError

ALL_SKILLS = ["陪诊", "保洁", "代办", "适老化评估", "助餐"]


@dataclass(frozen=True)
class AgentEnv:
    station_id: int
    staff_id: int
    staff_headers: dict
    other_staff_headers: dict
    customer: dict
    admin: dict
    elder_id: int
    empty_elder_id: int
    services: dict[str, dict]
    in_service_order_id: int
    assigned_order_id: int


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


def _scheduled(days: int) -> str:
    day = datetime.now(business_tz()).date() + timedelta(days=days)
    return datetime.combine(day, datetime.min.time(), tzinfo=business_tz()).replace(
        hour=9
    ).isoformat()


@pytest.fixture(scope="module")
def env(client: TestClient) -> AgentEnv:
    admin = _admin(client)
    suffix = int(time.time_ns()) % 10**8

    station = client.post(
        "/api/v1/admin/stations",
        headers=admin,
        json={
            "name": f"Agent测试站{suffix}",
            "street": "Agent测试街道",
            "address": "Agent测试社区 1 号",
        },
    )
    assert station.status_code == 201, station.text
    station_id = station.json()["id"]

    def new_staff(label: str, phone: str) -> int:
        resp = client.post(
            "/api/v1/admin/staff",
            headers=admin,
            json={
                "name": f"Agent员工{label}{suffix}",
                "phone": phone,
                "skills": ALL_SKILLS,
                "station_id": station_id,
            },
        )
        assert resp.status_code == 201, resp.text
        return resp.json()["id"]

    staff_id = new_staff("A", f"139{suffix}8")
    other_staff_id = new_staff("B", f"139{suffix}7")

    # 后台建员工不带密码，测试补一个；客户也自建，避免污染其它用例的老人列表
    customer_phone = f"135{suffix:08d}"
    with SessionLocal() as db:
        for uid in (staff_id, other_staff_id):
            user = db.get(User, uid)
            user.password_hash = hash_password("123456")
        db.add(
            User(
                phone=customer_phone,
                name=f"Agent客户{suffix}",
                role="customer",
                password_hash=hash_password("123456"),
            )
        )
        db.commit()

    staff_headers = _login(
        client, "/api/v1/auth/login", {"phone": f"139{suffix}8", "password": "123456"}
    )
    other_staff_headers = _login(
        client, "/api/v1/auth/login", {"phone": f"139{suffix}7", "password": "123456"}
    )
    customer = _login(
        client, "/api/v1/auth/login", {"phone": customer_phone, "password": "123456"}
    )

    def new_elder(label: str, health_notes: str) -> int:
        resp = client.post(
            "/api/v1/elders",
            headers=customer,
            json={
                "name": f"Agent长辈{label}{suffix}",
                "gender": "male",
                "birth_year": 1948,
                "phone": f"137{suffix:08d}",
                "community": "Agent测试社区",
                "address": "Agent测试社区 3 栋 202",
                "health_notes": health_notes,
                "emergency_name": "测试家属",
                # 手机号会在 prompt 前被脱敏，这里留一个可断言的敏感串
                "emergency_phone": "13812345678",
                "station_id": station_id,
            },
        )
        assert resp.status_code == 201, resp.text
        return resp.json()["id"]

    elder_id = new_elder("甲", "高血压、糖尿病，长期服药，家属电话 13812345678")
    empty_elder_id = new_elder("乙", "")

    services = {item["code"]: item for item in client.get("/api/v1/services").json()}

    def prepare_order(elder: int, *, start: bool, days: int) -> int:
        created = client.post(
            "/api/v1/orders",
            headers=customer,
            json={
                "elder_id": elder,
                "service_id": services["companion"]["id"],
                "scheduled_at": _scheduled(days),
            },
        )
        assert created.status_code == 201, created.text
        order_id = created.json()["id"]
        assert client.post(f"/api/v1/orders/{order_id}/confirm", headers=admin).status_code == 200
        assigned = client.post(
            f"/api/v1/orders/{order_id}/assign",
            headers=admin,
            json={"staff_id": staff_id},
        )
        assert assigned.status_code == 200, assigned.text
        assert client.post(f"/api/v1/orders/{order_id}/pay", headers=customer).status_code == 200
        assert (
            client.post(f"/api/v1/orders/{order_id}/accept", headers=staff_headers).status_code
            == 200
        )
        if start:
            started = client.post(f"/api/v1/orders/{order_id}/start", headers=staff_headers)
            assert started.status_code == 200, started.text
        return order_id

    in_service_order_id = prepare_order(elder_id, start=True, days=1)
    assigned_order_id = prepare_order(empty_elder_id, start=False, days=2)

    yield AgentEnv(
        station_id=station_id,
        staff_id=staff_id,
        staff_headers=staff_headers,
        other_staff_headers=other_staff_headers,
        customer=customer,
        admin=admin,
        elder_id=elder_id,
        empty_elder_id=empty_elder_id,
        services=services,
        in_service_order_id=in_service_order_id,
        assigned_order_id=assigned_order_id,
    )

    client.patch(f"/api/v1/admin/stations/{station_id}", headers=admin, json={"active": False})


def _rows(user_id: int, scenario: str) -> list[AgentAction]:
    with SessionLocal() as db:
        return list(
            db.scalars(
                select(AgentAction)
                .where(AgentAction.user_id == user_id, AgentAction.scenario == scenario)
                .order_by(AgentAction.id)
            )
        )


# ------------------------------------------------------------------ 主流程
def test_status_reports_enabled_and_quota(client: TestClient, env: AgentEnv) -> None:
    resp = client.get("/api/v1/agent/status", headers=env.staff_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["enabled"] is True
    assert body["provider"] == "mock"
    assert body["daily_limit"] == settings.agent_daily_limit_per_user
    assert body["remaining"] >= 0


def test_record_draft_returns_five_sections_and_audits(
    client: TestClient, env: AgentEnv
) -> None:
    before = len(_rows(env.staff_id, "record_draft"))
    resp = client.post(
        "/api/v1/agent/staff/record-draft",
        headers=env.staff_headers,
        json={
            "order_id": env.in_service_order_id,
            "rough_notes": "陪老人复查，医生让继续吃药，下周三再来，取了两盒药",
            "photo_count": 2,
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["content"]
    for section in ("服务内容：", "老人状态：", "异常与风险：", "下次安排：", "照片："):
        assert section in body["content"]
    assert 2 <= len(body["prep_brief"]) <= 5
    assert body["model"] == "mock"

    rows = _rows(env.staff_id, "record_draft")
    assert len(rows) - before == 2  # 模型调用 1 行 + 请求汇总 1 行
    llm_row, summary_row = rows[-2], rows[-1]
    assert llm_row.trace_id == summary_row.trace_id
    assert llm_row.step < summary_row.step
    assert summary_row.payload["order_id"] == env.in_service_order_id
    # 白名单：审计里不能出现口述原文或任何手机号
    dumped = json.dumps([row.payload for row in rows], ensure_ascii=False)
    assert "两盒药" not in dumped
    assert "13812345678" not in dumped
    assert len(llm_row.payload_digest) == 64


def test_record_draft_rejects_other_staff_and_wrong_status(
    client: TestClient, env: AgentEnv
) -> None:
    body = {"order_id": env.in_service_order_id, "rough_notes": "测试"}
    forbidden = client.post(
        "/api/v1/agent/staff/record-draft", headers=env.other_staff_headers, json=body
    )
    assert forbidden.status_code == 403, forbidden.text

    # 已派单但未开始服务：记录草稿必须拒绝，避免提前生成不实内容
    conflict = client.post(
        "/api/v1/agent/staff/record-draft",
        headers=env.staff_headers,
        json={"order_id": env.assigned_order_id, "rough_notes": "测试"},
    )
    assert conflict.status_code == 409, conflict.text

    empty = client.post(
        "/api/v1/agent/staff/record-draft",
        headers=env.staff_headers,
        json={"order_id": env.in_service_order_id, "rough_notes": "   "},
    )
    assert empty.status_code == 422, empty.text


def test_redline_short_circuits_without_model_call(client: TestClient, env: AgentEnv) -> None:
    before = _rows(env.staff_id, "record_draft")
    resp = client.post(
        "/api/v1/agent/staff/record-draft",
        headers=env.staff_headers,
        json={
            "order_id": env.in_service_order_id,
            "rough_notes": "老人突然胸痛、喘不上气，已联系家属",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["content"] == policies.REDLINE_REPLY
    assert "redline" in body["warnings"]

    rows = _rows(env.staff_id, "record_draft")
    # 只应多出汇总行：急症场景不产生模型调用，也不占额度
    assert len(rows) - len(before) == 1
    assert rows[-1].payload["warnings"] == ["redline"]


def test_prep_brief_and_empty_profile(client: TestClient, env: AgentEnv) -> None:
    resp = client.post(
        "/api/v1/agent/staff/prep-brief",
        headers=env.staff_headers,
        json={"order_id": env.in_service_order_id},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert 2 <= len(body["items"]) <= 5
    dumped = json.dumps(_rows(env.staff_id, "prep_brief")[-1].payload, ensure_ascii=False)
    assert "13812345678" not in dumped

    before = len(_rows(env.staff_id, "prep_brief"))
    empty = client.post(
        "/api/v1/agent/staff/prep-brief",
        headers=env.staff_headers,
        json={"order_id": env.assigned_order_id},
    )
    assert empty.status_code == 200, empty.text
    assert empty.json()["items"] == []
    # 档案为空只写汇总行，不产生模型调用
    assert len(_rows(env.staff_id, "prep_brief")) - before == 1

    forbidden = client.post(
        "/api/v1/agent/staff/prep-brief",
        headers=env.other_staff_headers,
        json={"order_id": env.in_service_order_id},
    )
    assert forbidden.status_code == 403


def test_quota_exhausted_returns_429(
    client: TestClient, env: AgentEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    used = client.get("/api/v1/agent/status", headers=env.staff_headers).json()["used_today"]
    monkeypatch.setattr(settings, "agent_daily_limit_per_user", used + 1)
    first = client.post(
        "/api/v1/agent/staff/prep-brief",
        headers=env.staff_headers,
        json={"order_id": env.in_service_order_id},
    )
    assert first.status_code == 200, first.text
    second = client.post(
        "/api/v1/agent/staff/prep-brief",
        headers=env.staff_headers,
        json={"order_id": env.in_service_order_id},
    )
    assert second.status_code == 429, second.text
    assert second.json()["code"] == "agent_rate_limited"


def test_disabled_returns_503(
    client: TestClient, env: AgentEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "agent_enabled", False)
    status = client.get("/api/v1/agent/status", headers=env.staff_headers)
    assert status.status_code == 200 and status.json()["enabled"] is False
    resp = client.post(
        "/api/v1/agent/staff/prep-brief",
        headers=env.staff_headers,
        json={"order_id": env.in_service_order_id},
    )
    assert resp.status_code == 503
    assert resp.json()["code"] == "agent_unavailable"


# -------------------------------------------------------------- 适配器单测
class _StubResponse:
    def __init__(self, status_code: int, text: str = "") -> None:
        self.status_code = status_code
        self.text = text

    def json(self) -> dict:
        return {}


class _StubClient:
    def __init__(self, response: _StubResponse | None = None, exc: Exception | None = None):
        self._response = response
        self._exc = exc

    def post(self, *args, **kwargs):
        if self._exc:
            raise self._exc
        return self._response


def _model() -> agent_models.CommunityChatModel:
    return agent_models.CommunityChatModel(
        model_name="deepseek-flash",
        base_url="https://api.example.com",
        api_key="test-key",
        timeout_seconds=1,
    )


def test_adapter_payload_disables_thinking() -> None:
    """混合思考模型必须显式关推理，否则 token 全花在思考上、JSON 会被截断。"""
    model = _model()
    payload = model._payload([], stop=None, stream=False)
    assert payload["thinking"] == {"type": "disabled"}
    assert payload["response_format"] == {"type": "json_object"}

    # 网关不认该字段时，配置项关掉后请求体里不应再出现
    plain = _model().model_copy(update={"disable_thinking": False})
    assert "thinking" not in plain._payload([], stop=None, stream=False)


def test_adapter_maps_http_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(agent_models, "_CLIENT", _StubClient(_StubResponse(500, "boom")))
    with pytest.raises(AgentUnavailableError):
        _model().invoke("测试")

    monkeypatch.setattr(agent_models, "_CLIENT", _StubClient(_StubResponse(429, "slow down")))
    with pytest.raises(AgentRateLimitedError):
        _model().invoke("测试")

    monkeypatch.setattr(
        agent_models, "_CLIENT", _StubClient(exc=httpx.TimeoutException("timeout"))
    )
    with pytest.raises(AgentUnavailableError):
        _model().invoke("测试")


def test_policies_scrub_parse_and_medical_guard() -> None:
    scrubbed = policies.scrub("家属电话 13812345678，住 3 栋 202")
    assert "13812345678" not in scrubbed
    assert "3 栋" not in scrubbed

    payload = policies.parse_json_object(
        '```json\n{"content": "服务内容：x。建议加量服用。", "prep_brief": ["a", "b"]}\n```'
    )
    content, items, warnings = policies.guard_record_output(payload)
    assert "加量" not in content
    assert "medical_guard" in warnings
    assert items == ["a", "b"]

    assert policies.parse_json_object("不是 JSON") is None
    assert policies.hit_redline("老人胸痛") is True
