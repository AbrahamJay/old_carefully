"""阶段六：管理端解释场景（派单说明 / 异常解释）。

验收口径：
- 人由规则选出，模型只解释：推荐人恒等于候选第一名，模型给的 staff_id 不生效；
- 无候选 / 任务已收敛时不调模型，只写汇总行；
- 同一主体、同一事实在 TTL 内复用缓存，force_refresh 可强制重新生成；
- 角色与开关、配额照常护栏；
- 护栏拒绝时整单回退规则文案（source=rule），前端永远有内容；
- 审计不落手机号、门牌等原始信息。
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import settings
from app.core.security import hash_password
from app.core.time import business_tz, utcnow
from app.db.models import AdminTask, AgentAction, User
from app.db.session import SessionLocal
from app.main import app
from app.modules.agents import policies

ALL_SKILLS = ["陪诊", "保洁", "代办", "适老化评估", "助餐"]
SUMMARY_STEP = 90


@dataclass(frozen=True)
class AdminEnv:
    admin: dict
    staff_headers: dict
    order_id: int
    empty_order_id: int
    open_task_id: int
    closed_task_id: int


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


def _scheduled(days: int) -> str:
    day = datetime.now(business_tz()).date() + timedelta(days=days)
    return (
        datetime.combine(day, datetime.min.time(), tzinfo=business_tz())
        .replace(hour=9)
        .isoformat()
    )


@pytest.fixture(scope="module")
def env(client: TestClient) -> AdminEnv:
    admin = _login(
        client,
        "/api/v1/auth/admin/login",
        {"username": "13900000000", "password": "Admin123!"},
    )
    suffix = int(time.time_ns()) % 10**8
    community = f"管理解释社区{suffix}"

    def new_station(label: str) -> int:
        resp = client.post(
            "/api/v1/admin/stations",
            headers=admin,
            json={
                "name": f"管理解释站{label}{suffix}",
                "street": community,
                "address": f"{community} 1 号",
            },
        )
        assert resp.status_code == 201, resp.text
        return resp.json()["id"]

    station_id = new_station("甲")
    # 没有员工的站点：用来说明「无候选」不调模型
    empty_station_id = new_station("乙")

    staff_id = client.post(
        "/api/v1/admin/staff",
        headers=admin,
        json={
            "name": f"管理解释员工{suffix}",
            "phone": f"139{suffix}8",
            "skills": ALL_SKILLS,
            "station_id": station_id,
        },
    )
    assert staff_id.status_code == 201, staff_id.text
    staff_id = staff_id.json()["id"]

    customer_phone = f"135{suffix:08d}"
    with SessionLocal() as db:
        staff_user = db.get(User, staff_id)
        staff_user.password_hash = hash_password("123456")
        db.add(
            User(
                phone=customer_phone,
                name=f"管理解释客户{suffix}",
                role="customer",
                password_hash=hash_password("123456"),
            )
        )
        db.commit()

    staff_headers = _login(
        client, "/api/v1/auth/login", {"phone": f"139{suffix}8", "password": "123456"}
    )
    customer = _login(
        client, "/api/v1/auth/login", {"phone": customer_phone, "password": "123456"}
    )

    def new_elder(label: str, station: int) -> int:
        resp = client.post(
            "/api/v1/elders",
            headers=customer,
            json={
                "name": f"管理解释长辈{label}{suffix}",
                "gender": "male",
                "birth_year": 1946,
                "phone": f"137{suffix:08d}",
                "community": community,
                "address": f"{community} 3 栋 202",
                "health_notes": "高血压，家属电话 13812345678",
                "emergency_name": "测试家属",
                "emergency_phone": "13812345678",
                "station_id": station,
            },
        )
        assert resp.status_code == 201, resp.text
        return resp.json()["id"]

    elder_id = new_elder("甲", station_id)
    empty_elder_id = new_elder("乙", empty_station_id)

    services = {item["code"]: item for item in client.get("/api/v1/services").json()}

    def new_order(elder: int) -> int:
        resp = client.post(
            "/api/v1/orders",
            headers=customer,
            json={
                "elder_id": elder,
                "service_id": services["companion"]["id"],
                "scheduled_at": _scheduled(2),
            },
        )
        assert resp.status_code == 201, resp.text
        return resp.json()["id"]

    order_id = new_order(elder_id)
    empty_order_id = new_order(empty_elder_id)

    # 直接落两条任务：扫描规则已写好 detail，解释场景只读不改
    detail = {
        "rule": "assigned_not_accepted",
        "why": "订单已派出 90 分钟，服务人员仍未接单。",
        "suggest": "先电话联系服务人员确认是否可接",
        "elapsed_minutes": 90,
        "threshold_minutes": 30,
        "facts": {
            "assigned_at": _scheduled(2),
            "staff_phone": "13812345678",
            "address": f"{community} 3 栋 202",
        },
    }
    now = utcnow()
    with SessionLocal() as db:
        open_task = AdminTask(
            type="assigned_not_accepted",
            order_id=order_id,
            severity="high",
            status="open",
            dedupe_key=f"test_explain_{suffix}_open",
            title="订单已派出仍未接单",
            detail=detail,
            detected_at=now,
        )
        closed_task = AdminTask(
            type="assigned_not_accepted",
            order_id=order_id,
            severity="medium",
            status="handled",
            dedupe_key=f"test_explain_{suffix}_closed",
            title="订单已派出仍未接单",
            detail=detail,
            detected_at=now,
            handled_at=now,
            note="测试已处理",
        )
        db.add_all([open_task, closed_task])
        db.commit()
        open_task_id = open_task.id
        closed_task_id = closed_task.id

    yield AdminEnv(
        admin=admin,
        staff_headers=staff_headers,
        order_id=order_id,
        empty_order_id=empty_order_id,
        open_task_id=open_task_id,
        closed_task_id=closed_task_id,
    )

    client.patch(
        f"/api/v1/admin/stations/{station_id}", headers=admin, json={"active": False}
    )


def _trace_rows(trace_id: str) -> list[AgentAction]:
    with SessionLocal() as db:
        return list(
            db.scalars(
                select(AgentAction)
                .where(AgentAction.trace_id == trace_id)
                .order_by(AgentAction.id)
            )
        )


# --------------------------------------------------------------- 状态与角色
def test_status_exposes_admin_scenarios(client: TestClient, env: AdminEnv) -> None:
    admin_body = client.get("/api/v1/agent/status", headers=env.admin).json()
    assert admin_body["admin_scenarios"] == ["dispatch_suggest", "task_explain"]
    assert admin_body["admin_daily_limit"] == settings.agent_admin_daily_limit_per_user
    assert admin_body["admin_remaining"] >= 0

    staff_body = client.get("/api/v1/agent/status", headers=env.staff_headers).json()
    # 员工看不到管理端入口：前端据此隐藏按钮
    assert staff_body["admin_scenarios"] == []


def test_admin_endpoints_reject_staff(client: TestClient, env: AdminEnv) -> None:
    dispatch = client.post(
        "/api/v1/agent/admin/dispatch-suggest",
        headers=env.staff_headers,
        json={"order_id": env.order_id},
    )
    assert dispatch.status_code == 403, dispatch.text

    explain = client.post(
        "/api/v1/agent/admin/task-explain",
        headers=env.staff_headers,
        json={"task_id": env.open_task_id},
    )
    assert explain.status_code == 403, explain.text


# ----------------------------------------------------------------- 派单解释
def test_dispatch_suggest_llm_then_cache(client: TestClient, env: AdminEnv) -> None:
    candidates_body = client.get(
        f"/api/v1/admin/orders/{env.order_id}/candidates", headers=env.admin
    )
    assert candidates_body.status_code == 200, candidates_body.text
    candidates = candidates_body.json()
    assert candidates["candidates"], candidates
    top = candidates["candidates"][0]

    first = client.post(
        "/api/v1/agent/admin/dispatch-suggest",
        headers=env.admin,
        json={"order_id": env.order_id},
    )
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["source"] == "llm"
    # 推荐人恒为规则第一名，mock 没回 staff_id 也不影响
    assert body["recommendation"]["staff_id"] == top["staff_id"]
    assert body["summary"]
    assert body["why"]
    assert body["data_gaps"] == candidates["data_gaps"]
    assert "staff_id_defaulted" in body["warnings"]
    assert len(body["trace_id"]) == 32

    rows = _trace_rows(body["trace_id"])
    assert len(rows) == 2  # 模型调用 1 行 + 请求汇总 1 行
    llm_row, summary_row = rows
    assert llm_row.step < SUMMARY_STEP
    assert summary_row.step == SUMMARY_STEP
    assert summary_row.thread_id == f"dispatch_suggest:{env.order_id}"
    assert summary_row.payload["source"] == "llm"
    assert summary_row.payload["output"]["summary"] == body["summary"]

    # 事实未变：第二次命中缓存，不产生新的模型调用
    second = client.post(
        "/api/v1/agent/admin/dispatch-suggest",
        headers=env.admin,
        json={"order_id": env.order_id},
    )
    assert second.status_code == 200, second.text
    cached = second.json()
    assert cached["source"] == "cache"
    assert cached["trace_id"] == body["trace_id"]
    assert cached["facts_hash"] == body["facts_hash"]
    assert len(_trace_rows(cached["trace_id"])) == 2

    # force_refresh：跳过缓存重新生成
    refreshed = client.post(
        "/api/v1/agent/admin/dispatch-suggest",
        headers=env.admin,
        json={"order_id": env.order_id, "force_refresh": True},
    )
    assert refreshed.status_code == 200, refreshed.text
    assert refreshed.json()["source"] == "llm"
    assert refreshed.json()["trace_id"] != body["trace_id"]


def test_dispatch_suggest_without_candidates(client: TestClient, env: AdminEnv) -> None:
    resp = client.post(
        "/api/v1/agent/admin/dispatch-suggest",
        headers=env.admin,
        json={"order_id": env.empty_order_id},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # 没有事实可解释，直接走规则文案，不产生模型调用
    assert body["source"] == "rule"
    assert body["recommendation"] is None
    assert body["warnings"] == ["no_candidates"]
    assert body["excluded"]
    rows = _trace_rows(body["trace_id"])
    assert len(rows) == 1 and rows[0].step == SUMMARY_STEP


# ----------------------------------------------------------------- 异常解释
def test_task_explain_guard_and_escalate(client: TestClient, env: AdminEnv) -> None:
    resp = client.post(
        "/api/v1/agent/admin/task-explain",
        headers=env.admin,
        json={"task_id": env.open_task_id},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["source"] == "llm"
    assert body["what_happened"]
    assert body["next_actions"]
    for item in body["next_actions"]:
        assert item["action"] in policies.ALLOWED_TASK_ACTIONS
    # 高优先级且超过两倍阈值：模型说 false 也必须升级
    assert body["escalate"] is True

    # 审计只留解释结果，手机号与门牌不能出现在任何一行
    dumped = json.dumps([row.payload for row in _trace_rows(body["trace_id"])], ensure_ascii=False)
    assert "13812345678" not in dumped
    assert "3 栋" not in dumped

    cached = client.post(
        "/api/v1/agent/admin/task-explain",
        headers=env.admin,
        json={"task_id": env.open_task_id},
    )
    assert cached.status_code == 200, cached.text
    assert cached.json()["source"] == "cache"


def test_task_explain_closed_task_short_circuits(
    client: TestClient, env: AdminEnv
) -> None:
    resp = client.post(
        "/api/v1/agent/admin/task-explain",
        headers=env.admin,
        json={"task_id": env.closed_task_id},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["source"] == "rule"
    assert body["warnings"] == ["task_closed"]
    rows = _trace_rows(body["trace_id"])
    assert len(rows) == 1 and rows[0].step == SUMMARY_STEP


# --------------------------------------------------------------- 开关与配额
def test_disabled_returns_503(
    client: TestClient, env: AdminEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "agent_enabled", False)
    status = client.get("/api/v1/agent/status", headers=env.admin)
    assert status.status_code == 200
    assert status.json()["admin_scenarios"] == []

    resp = client.post(
        "/api/v1/agent/admin/dispatch-suggest",
        headers=env.admin,
        json={"order_id": env.order_id},
    )
    assert resp.status_code == 503
    assert resp.json()["code"] == "agent_unavailable"


def test_admin_quota_exhausted_returns_429(
    client: TestClient, env: AdminEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    used = client.get("/api/v1/agent/status", headers=env.admin).json()["used_today"]
    monkeypatch.setattr(settings, "agent_admin_daily_limit_per_user", used + 1)

    first = client.post(
        "/api/v1/agent/admin/dispatch-suggest",
        headers=env.admin,
        json={"order_id": env.order_id, "force_refresh": True},
    )
    assert first.status_code == 200, first.text
    second = client.post(
        "/api/v1/agent/admin/dispatch-suggest",
        headers=env.admin,
        json={"order_id": env.order_id, "force_refresh": True},
    )
    assert second.status_code == 429, second.text
    assert second.json()["code"] == "agent_rate_limited"


# ----------------------------------------------------------------- 护栏单测
def _candidates() -> list[dict]:
    return [
        {"staff_id": 11, "name": "张阿姨", "score": 92},
        {"staff_id": 12, "name": "李师傅", "score": 80},
    ]


def test_guard_dispatch_rejects_staff_conflict_and_invalid() -> None:
    facts_text = json.dumps(_candidates(), ensure_ascii=False)

    conflict, warnings = policies.guard_dispatch_output(
        {"staff_id": 12, "summary": "推荐李师傅", "why": ["同站点"]},
        candidates=_candidates(),
        rule_gaps=["老人未维护社区"],
        facts_text=facts_text,
    )
    assert conflict == {"staff_id": None}
    assert warnings == ["staff_conflict"]

    invalid, warnings = policies.guard_dispatch_output(
        {"staff_id": 99, "summary": "推荐他人", "why": ["同站点"]},
        candidates=_candidates(),
        rule_gaps=[],
        facts_text=facts_text,
    )
    assert invalid == {"staff_id": None}
    assert warnings == ["staff_id_invalid"]

    # 数字必须能在事实里找到：凭空写「15 分钟」直接判不合格
    hallucinated, warnings = policies.guard_dispatch_output(
        {"staff_id": 11, "summary": "预计 15 分钟到达", "why": ["同站点"]},
        candidates=_candidates(),
        rule_gaps=[],
        facts_text=facts_text,
    )
    assert hallucinated == {"staff_id": None}
    assert warnings == ["summary_invalid"]


def test_guard_dispatch_keeps_rule_gaps_and_top_staff() -> None:
    result, warnings = policies.guard_dispatch_output(
        {
            "staff_id": 11,
            "summary": "技能与负载均合适",
            "why": ["同站点", "评分 92"],
            "risks": [],
            # 模型多写的数据缺口必须被丢弃
            "data_gaps": ["模型编的缺口"],
            "alternatives": [{"staff_id": 12, "name": "模型写的名字", "note": "评分 80"}],
        },
        candidates=_candidates(),
        rule_gaps=["老人未维护社区"],
        facts_text=json.dumps(_candidates(), ensure_ascii=False),
    )
    assert result["staff_id"] == 11
    assert result["data_gaps"] == ["老人未维护社区"]
    # 姓名以候选名单为准
    assert result["alternatives"][0]["name"] == "李师傅"
    assert warnings == []


def test_guard_task_output_drops_unknown_actions() -> None:
    result, warnings = policies.guard_task_output(
        {
            "what_happened": "订单已派出但未接单",
            "why": "超过阈值",
            "next_actions": [
                {"action": "launch_missile", "label": "越界动作"},
                {"action": "call_staff", "label": "联系服务人员"},
            ],
            "escalate": False,
            "data_gaps": [],
        },
        rule_why="订单已派出 90 分钟仍未接单",
        rule_suggest="先电话联系",
        severity="high",
        elapsed_minutes=90,
        threshold_minutes=30,
        facts_text="订单已派出 90 分钟，阈值 30 分钟",
    )
    assert [item["action"] for item in result["next_actions"]] == ["call_staff"]
    assert "action_not_allowed" in warnings
    assert result["escalate"] is True

    # 解析失败：动作退回人工核查，不把空动作交给前端
    fallback, warnings = policies.guard_task_output(
        None,
        rule_why="规则原因",
        rule_suggest="人工确认",
        severity="medium",
        elapsed_minutes=10,
        threshold_minutes=30,
        facts_text="",
    )
    assert fallback == {}
    assert warnings == ["bad_output"]


def test_facts_hash_and_scrub_tree() -> None:
    facts = {"order": {"note": "3 栋 202", "staff_phone": "13812345678"}}
    scrubbed = policies.scrub_tree(facts)
    assert "3 栋" not in json.dumps(scrubbed, ensure_ascii=False)
    assert "13812345678" not in json.dumps(scrubbed, ensure_ascii=False)

    assert policies.facts_hash(facts) == policies.facts_hash(dict(facts))
    assert policies.facts_hash(facts) != policies.facts_hash({"order": {"note": "变了"}})