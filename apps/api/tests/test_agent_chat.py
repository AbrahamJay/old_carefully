"""阶段七：员工「这单助手」（绑定单张订单的窄问答 + SSE）。

验收要点：
- JSON 与 SSE 两条路径都能用，且 SSE 帧序为 meta → delta* → done；
- 急症与越界问题由代码直接回答，不调模型、不占额度；
- 对话额度和写记录额度互不挤占；
- 审计不落问题原文与回答原文，回答里不出现手机号/门牌。
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
from app.core.time import business_tz
from app.db.models import AgentAction, User
from app.db.session import SessionLocal
from app.main import app
from app.modules.agents import models, policies, tools
from app.modules.agents import runtime as agent_runtime

ALL_SKILLS = ["陪诊", "保洁", "代办", "适老化评估", "助餐"]
SUMMARY_STEP = 90


@dataclass(frozen=True)
class ChatEnv:
    staff_id: int
    staff_headers: dict
    other_staff_headers: dict
    admin: dict
    in_service_order_id: int
    pending_order_id: int
    completed_order_id: int


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
    return datetime.combine(day, datetime.min.time(), tzinfo=business_tz()).replace(
        hour=9
    ).isoformat()


def _frames(body: str) -> list[dict]:
    """按 SSE 的空行切帧，取出每帧的 data（前端解析逻辑与此一致）。"""
    items: list[dict] = []
    for block in body.split("\n\n"):
        line = next(
            (row for row in block.splitlines() if row.startswith("data:")), None
        )
        if line:
            items.append(json.loads(line[len("data:") :].strip()))
    return items


def _trace_rows(trace_id: str) -> list[AgentAction]:
    with SessionLocal() as db:
        return list(
            db.scalars(
                select(AgentAction)
                .where(AgentAction.trace_id == trace_id)
                .order_by(AgentAction.id)
            )
        )


@pytest.fixture(scope="module")
def env(client: TestClient) -> ChatEnv:
    admin = _login(
        client,
        "/api/v1/auth/admin/login",
        {"username": "13900000000", "password": "Admin123!"},
    )
    suffix = int(time.time_ns()) % 10**8

    station = client.post(
        "/api/v1/admin/stations",
        headers=admin,
        json={
            "name": f"对话测试站{suffix}",
            "street": "对话测试街道",
            "address": "对话测试社区 1 号",
        },
    )
    assert station.status_code == 201, station.text
    station_id = station.json()["id"]

    def new_staff(label: str, phone: str) -> int:
        resp = client.post(
            "/api/v1/admin/staff",
            headers=admin,
            json={
                "name": f"对话员工{label}{suffix}",
                "phone": phone,
                "skills": ALL_SKILLS,
                "station_id": station_id,
            },
        )
        assert resp.status_code == 201, resp.text
        return resp.json()["id"]

    staff_id = new_staff("A", f"139{suffix}8")
    other_id = new_staff("B", f"139{suffix}7")

    # 自建客户与老人：复用 seed 数据会被其它用例的 elders 列表排序影响
    customer_phone = f"136{suffix:08d}"
    with SessionLocal() as db:
        for uid in (staff_id, other_id):
            user = db.get(User, uid)
            user.password_hash = hash_password("123456")
        db.add(
            User(
                phone=customer_phone,
                name=f"对话客户{suffix}",
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

    elder = client.post(
        "/api/v1/elders",
        headers=customer,
        json={
            "name": f"对话长辈{suffix}",
            "gender": "female",
            "birth_year": 1945,
            "phone": f"137{suffix:08d}",
            "community": "对话测试社区",
            "address": "对话测试社区 3 栋 202",
            "health_notes": "高血压，长期服药；家属电话 13812345678",
            "emergency_name": "测试家属",
            "emergency_phone": "13812345678",
            "station_id": station_id,
        },
    )
    assert elder.status_code == 201, elder.text
    elder_id = elder.json()["id"]
    services = {item["code"]: item for item in client.get("/api/v1/services").json()}

    def new_order(*, confirm: bool, days: int) -> int:
        created = client.post(
            "/api/v1/orders",
            headers=customer,
            json={
                "elder_id": elder_id,
                "service_id": services["companion"]["id"],
                "scheduled_at": _scheduled(days),
            },
        )
        assert created.status_code == 201, created.text
        order_id = created.json()["id"]
        if not confirm:
            return order_id
        assert (
            client.post(f"/api/v1/orders/{order_id}/confirm", headers=admin).status_code
            == 200
        )
        assigned = client.post(
            f"/api/v1/orders/{order_id}/assign",
            headers=admin,
            json={"staff_id": staff_id},
        )
        assert assigned.status_code == 200, assigned.text
        assert (
            client.post(f"/api/v1/orders/{order_id}/pay", headers=customer).status_code
            == 200
        )
        assert (
            client.post(f"/api/v1/orders/{order_id}/accept", headers=staff_headers).status_code
            == 200
        )
        started = client.post(f"/api/v1/orders/{order_id}/start", headers=staff_headers)
        assert started.status_code == 200, started.text
        return order_id

    def complete(order_id: int) -> int:
        """跑完整单：问答场景应该拒绝已完成的单（事实已定，问了也没用）。"""
        assert (
            client.post(
                f"/api/v1/orders/{order_id}/records",
                headers=staff_headers,
                json={"content": "已陪诊", "photos": [], "elder_confirmed": False},
            ).status_code
            == 201
        )
        done = client.post(f"/api/v1/orders/{order_id}/complete", headers=staff_headers)
        assert done.status_code == 200, done.text
        return order_id

    in_service_order_id = new_order(confirm=True, days=1)

    yield ChatEnv(
        staff_id=staff_id,
        staff_headers=staff_headers,
        other_staff_headers=other_staff_headers,
        admin=admin,
        in_service_order_id=in_service_order_id,
        pending_order_id=new_order(confirm=False, days=2),
        completed_order_id=complete(new_order(confirm=True, days=3)),
    )


_CHAT_CALLS: list[dict] = []
_CHAT_PROMPTS: list[str] = []


class _RecordingChatModel(models.MockChatModel):
    """记录模型实际收到的参数与 prompt，用来盯住「调用点漏传开关」「facts 缺字段」这类回归。"""

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        _CHAT_CALLS.append(dict(kwargs))
        _CHAT_PROMPTS.append("\n".join(str(message.content) for message in messages))
        return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)


_CALLS = _CHAT_CALLS  # 测试里用短名


def _chat_used(client: TestClient, headers: dict) -> int:
    return client.get("/api/v1/agent/status", headers=headers).json()["chat_used_today"]


# ------------------------------------------------------------------ 主流程
def test_status_exposes_chat_entry_for_staff_only(client: TestClient, env: ChatEnv) -> None:
    staff_body = client.get("/api/v1/agent/status", headers=env.staff_headers).json()
    assert staff_body["chat_enabled"] is True
    assert staff_body["chat_daily_limit"] == settings.agent_chat_daily_limit_per_user
    assert staff_body["chat_remaining"] >= 0

    # 管理端已有解释场景，不再开一个聊天口
    admin_body = client.get("/api/v1/agent/status", headers=env.admin).json()
    assert admin_body["chat_enabled"] is False


def test_chat_json_answers_and_audits_without_text(client: TestClient, env: ChatEnv) -> None:
    resp = client.post(
        "/api/v1/agent/staff/chat",
        headers=env.staff_headers,
        json={
            "order_id": env.in_service_order_id,
            "question": "这单服务几点开始？",
            "history": [
                {"role": "user", "content": "这单是做什么的"},
                {"role": "assistant", "content": "是陪诊服务"},
            ],
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["source"] == "llm"
    assert body["intent"] == "order"
    assert body["answer"].strip()
    # 档案里的手机号与门牌不能出现在回答里
    assert "13812345678" not in body["answer"]
    assert "3 栋" not in body["answer"]
    assert body["remaining"] <= settings.agent_chat_daily_limit_per_user

    rows = _trace_rows(body["trace_id"])
    summary = [row for row in rows if row.step == SUMMARY_STEP]
    assert len(summary) == 1, [row.step for row in rows]
    assert summary[0].thread_id == f"chat:{env.in_service_order_id}"
    # 只记意图与字数：问题原文可能含老人姓名与病情，不能进审计
    payload = summary[0].payload
    assert payload["intent"] == "order"
    assert payload["answer_chars"] > 0
    assert "question" not in payload and "answer" not in payload


def test_chat_stream_emits_meta_delta_done(client: TestClient, env: ChatEnv) -> None:
    payload = {
        "order_id": env.in_service_order_id,
        "question": "老人有什么要注意的？",
        "history": [],
    }
    with client.stream(
        "POST",
        "/api/v1/agent/staff/chat/stream",
        headers=env.staff_headers,
        json=payload,
    ) as resp:
        assert resp.status_code == 200, resp.read()
        assert resp.headers["content-type"].startswith("text/event-stream")
        # nginx 必须看到这个头才不缓冲
        assert resp.headers["x-accel-buffering"] == "no"
        body = "".join(resp.iter_text())

    frames = _frames(body)
    assert frames[0]["type"] == "meta"
    assert frames[0]["source"] == "llm"
    assert frames[0]["intent"] == "elder"
    deltas = [item["text"] for item in frames if item["type"] == "delta"]
    assert deltas, frames
    assert frames[-1]["type"] == "done"
    # done 里的 answer 必须等于前端拼接结果，否则「重连/回填」会不一致
    assert frames[-1]["answer"] == "".join(deltas)
    assert isinstance(frames[-1]["remaining"], int)


def test_chat_redline_answers_without_model(client: TestClient, env: ChatEnv) -> None:
    before = _chat_used(client, env.staff_headers)
    resp = client.post(
        "/api/v1/agent/staff/chat",
        headers=env.staff_headers,
        json={"order_id": env.in_service_order_id, "question": "老人突然胸痛，喘不上气"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["source"] == "rule"
    assert "redline" in body["warnings"]
    assert "120" in body["answer"]
    # 固定回答不产生模型调用，也就不占额度
    assert _chat_used(client, env.staff_headers) == before
    steps = [row.step for row in _trace_rows(body["trace_id"])]
    assert steps == [SUMMARY_STEP]


def test_chat_out_of_scope_guides_to_station(client: TestClient, env: ChatEnv) -> None:
    resp = client.post(
        "/api/v1/agent/staff/chat",
        headers=env.staff_headers,
        json={"order_id": env.in_service_order_id, "question": "这单能退款吗"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["source"] == "rule"
    assert "out_of_scope" in body["warnings"]
    assert "站点管家" in body["answer"]


def test_chat_rejects_other_staff_and_admin(client: TestClient, env: ChatEnv) -> None:
    payload = {"order_id": env.in_service_order_id, "question": "这单几点开始"}
    forbidden = client.post(
        "/api/v1/agent/staff/chat", headers=env.other_staff_headers, json=payload
    )
    assert forbidden.status_code == 403

    rejected = client.post("/api/v1/agent/staff/chat", headers=env.admin, json=payload)
    assert rejected.status_code == 403


def test_chat_rejects_order_outside_scope(client: TestClient, env: ChatEnv) -> None:
    # 未派给自己的单：权限层直接 403，不让模型看到任何事实
    unassigned = client.post(
        "/api/v1/agent/staff/chat",
        headers=env.staff_headers,
        json={"order_id": env.pending_order_id, "question": "这单几点开始"},
    )
    assert unassigned.status_code == 403, unassigned.text

    # 已完成的单：事实已经定下，409 让前端刷新而不是让模型猜
    closed = client.post(
        "/api/v1/agent/staff/chat",
        headers=env.staff_headers,
        json={"order_id": env.completed_order_id, "question": "这单几点开始"},
    )
    assert closed.status_code == 409, closed.text


# ------------------------------------------------------------ 额度与开关
def test_chat_quota_does_not_eat_record_quota(
    client: TestClient, env: ChatEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    used = _chat_used(client, env.staff_headers)
    monkeypatch.setattr(settings, "agent_chat_daily_limit_per_user", used + 1)

    first = client.post(
        "/api/v1/agent/staff/chat",
        headers=env.staff_headers,
        json={"order_id": env.in_service_order_id, "question": "这单几点开始"},
    )
    assert first.status_code == 200, first.text
    second = client.post(
        "/api/v1/agent/staff/chat",
        headers=env.staff_headers,
        json={"order_id": env.in_service_order_id, "question": "这单几点开始"},
    )
    assert second.status_code == 429, second.text
    assert second.json()["code"] == "agent_rate_limited"

    # 对话额度用尽不影响写记录：两套额度按场景分开计数
    prep = client.post(
        "/api/v1/agent/staff/prep-brief",
        headers=env.staff_headers,
        json={"order_id": env.in_service_order_id},
    )
    assert prep.status_code == 200, prep.text


def test_chat_stream_disabled_returns_json_503(
    client: TestClient, env: ChatEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "agent_enabled", False)
    resp = client.post(
        "/api/v1/agent/staff/chat/stream",
        headers=env.staff_headers,
        json={"order_id": env.in_service_order_id, "question": "这单几点开始"},
    )
    # 校验在开流之前完成，所以还能拿到正常的 JSON 错误而不是半截流
    assert resp.status_code == 503
    assert resp.json()["code"] == "agent_unavailable"


def test_chat_redline_answered_even_when_quota_exhausted(
    client: TestClient, env: ChatEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    """急症指引不能被运营额度卡死：额度归零时普通问题 429，胸痛仍返回固定回复。"""
    used = _chat_used(client, env.staff_headers)
    monkeypatch.setattr(settings, "agent_chat_daily_limit_per_user", used)

    blocked = client.post(
        "/api/v1/agent/staff/chat",
        headers=env.staff_headers,
        json={"order_id": env.in_service_order_id, "question": "这单几点开始"},
    )
    assert blocked.status_code == 429, blocked.text

    resp = client.post(
        "/api/v1/agent/staff/chat",
        headers=env.staff_headers,
        json={"order_id": env.in_service_order_id, "question": "老人突然晕倒"},
    )
    assert resp.status_code == 200, resp.text
    assert "120" in resp.json()["answer"]
    # 短路不调模型也不查订单：额度不变
    assert _chat_used(client, env.staff_headers) == used


def test_admin_status_reports_admin_limit(client: TestClient, env: ChatEnv) -> None:
    """管理员看到的主额度必须是管理端上限，否则会出现「已用完却还能调」。"""
    body = client.get("/api/v1/agent/status", headers=env.admin).json()
    assert body["daily_limit"] == settings.agent_admin_daily_limit_per_user
    assert body["remaining"] == max(0, body["daily_limit"] - body["used_today"])
    assert body["admin_daily_limit"] == settings.agent_admin_daily_limit_per_user


def test_chat_requests_disable_json_mode(
    client: TestClient, env: ChatEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    """回归：对话必须显式关掉 json_mode。

    适配器默认 ``json_mode=True``（阶段五的结构化输出用），不关就会带上
    ``response_format=json_object``，与「不要 JSON」的 prompt 打架，
    真实网关只回空串或一串空格，前端表现为「(没有回答)」。
    """
    _CALLS.clear()
    monkeypatch.setattr(agent_runtime, "build_chat_model", lambda: _RecordingChatModel())
    payload = {"order_id": env.in_service_order_id, "question": "这单主要干些什么事情"}

    answered = client.post("/api/v1/agent/staff/chat", headers=env.staff_headers, json=payload)
    assert answered.status_code == 200, answered.text
    with client.stream(
        "POST", "/api/v1/agent/staff/chat/stream", headers=env.staff_headers, json=payload
    ) as resp:
        assert resp.status_code == 200
        "".join(resp.iter_text())

    assert len(_CALLS) == 2, _CALLS
    assert all(call.get("json_mode") is False for call in _CALLS), _CALLS


def test_chat_facts_include_area_without_door_number(
    client: TestClient, env: ChatEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    """回归：员工问「地址」时必须有地址可说，但只到街道+社区，门牌不发给模型。"""
    _CALLS.clear()
    _CHAT_PROMPTS.clear()
    monkeypatch.setattr(agent_runtime, "build_chat_model", lambda: _RecordingChatModel())

    resp = client.post(
        "/api/v1/agent/staff/chat",
        headers=env.staff_headers,
        json={"order_id": env.in_service_order_id, "question": "刚才说的地址再念一遍"},
    )
    assert resp.status_code == 200, resp.text

    prompt = _CHAT_PROMPTS[-1]
    assert "address_area" in prompt
    assert "对话测试街道" in prompt and "对话测试社区" in prompt
    # 档案地址是「对话测试社区 3 栋 202」：楼栋门牌不能进 prompt
    assert "3 栋" not in prompt and "3栋" not in prompt
    # 电话只给「有没有紧急联系人」这个布尔，号码不外发
    assert "emergency_available" in prompt
    assert "13812345678" not in prompt


def test_record_prompt_has_no_area() -> None:
    """写记录与服务前提示不需要位置：address_area 只在对话场景补回。"""
    facts = tools.OrderFacts(
        order_id=1,
        order_no="SO1",
        service_name="保洁",
        duration_minutes=60,
        scheduled_at="2026-11-27 09:00",
        order_status="in_service",
        community="幸福社区",
        elder_gender="女",
        elder_age=86,
        health_notes="",
        order_notes="",
        staff_name="王小明",
        address_area="和平街道 幸福社区",
    )
    assert "address_area" not in facts.to_prompt_dict()


# ------------------------------------------------------------- 纯函数护栏
def test_classify_chat_intent() -> None:
    assert policies.classify_chat_intent("这单几点到？") == policies.CHAT_INTENT_ORDER
    assert policies.classify_chat_intent("老人吃什么要注意吗") == policies.CHAT_INTENT_ELDER
    assert policies.classify_chat_intent("服务记录怎么写") == policies.CHAT_INTENT_FLOW
    assert policies.classify_chat_intent("能不能改派给别人") == policies.CHAT_INTENT_OUT_OF_SCOPE


def test_trim_chat_history_limits_and_scrubs() -> None:
    history = [
        {"role": "user", "content": f"问题{index}"} for index in range(10)
    ] + [{"role": "assistant", "content": "电话 13812345678"}]
    trimmed = policies.trim_chat_history(history, max_messages=3, max_chars=50)
    assert len(trimmed) == 3
    assert all("13812345678" not in item["content"] for item in trimmed)
    assert trimmed[-1]["content"] == "电话 ***"


def test_stream_guard_scrubs_phone_split_across_chunks() -> None:
    guard = policies.ChatStreamGuard(facts_text="{}")
    # 手机号被 chunk 边界劈开：没到句读就继续攒，不能先发出去半截
    assert guard.feed("家属电话 1381") == ""
    out = guard.feed("2345678。记得先联系。")
    assert "13812345678" not in out
    assert "***" in out
    # 最后一句没句读，仍在缓冲区，flush 时才放出
    assert guard.flush() == "记得先联系。"


def test_stream_guard_releases_long_text_without_punctuation() -> None:
    guard = policies.ChatStreamGuard(facts_text="{}")
    # 模型一直不打句读时不能干等：憋满 HOLD_CHARS 就放一段
    out = guard.feed("啊" * 70)
    assert len(out) == policies.ChatStreamGuard.HOLD_CHARS
    assert guard.flush() == "啊" * 10


def test_stream_guard_drops_medical_advice() -> None:
    guard = policies.ChatStreamGuard(facts_text="{}")
    out = guard.feed("可以先联系家属。建议停用降压药，注意观察。")
    assert "停药" not in out and "停用" not in out
    assert "联系家属" in out
    # 越界句是最后一句，flush 时整句丢弃并记告警
    assert guard.flush() == ""
    assert policies.CHAT_GUARD_WARNING in guard.warnings


def test_stream_guard_keeps_door_number_whole_at_cut() -> None:
    """切点不能落在门牌中间：「3号」+「楼」两半都匹配不到脱敏规则。"""
    hold = policies.ChatStreamGuard.HOLD_CHARS
    guard = policies.ChatStreamGuard(facts_text="{}")
    out = guard.feed("啊" * (hold - 2) + "3号楼见，记得先敲门。")
    out += guard.flush()
    assert "3号楼" not in out
    assert "***" in out


def test_stream_guard_drops_advice_inside_long_fragment() -> None:
    """无句读长片段里的越界措辞：既要拦下来，也不能留下「降压药」这种半截医嘱。"""
    hold = policies.ChatStreamGuard.HOLD_CHARS
    guard = policies.ChatStreamGuard(facts_text="{}")
    out = guard.feed("啊" * (hold - 1) + "建议停用降压药，注意观察" + "啊" * 30)
    out += guard.flush()
    assert "停用" not in out
    assert "降压药" not in out
    assert "啊" in out  # 其余文字照常下发，不会整段消失
    assert policies.CHAT_GUARD_WARNING in guard.warnings


def test_guard_hides_internal_terms_in_both_paths() -> None:
    """模型会把 prompt 里的 facts 当人话说出来，两条路径都要换成人话。"""
    answer, _ = policies.guard_chat_text("不知道，facts 里没有家属电话。", facts_text="{}")
    assert "facts" not in answer
    assert "订单信息里没有家属电话" in answer

    guard = policies.ChatStreamGuard(facts_text="{}")
    streamed = guard.feed("不知道，facts 里没有家属电话。")
    streamed += guard.flush()
    assert "facts" not in streamed
    assert "订单信息里没有家属电话" in streamed


def test_trim_chat_history_rewrites_internal_terms() -> None:
    """历史里带着上一轮漏出的 facts，不洗掉会被本轮原样模仿。"""
    trimmed = policies.trim_chat_history(
        [{"role": "assistant", "content": "不知道，facts 里没有家属电话"}],
        max_messages=2,
        max_chars=100,
    )
    assert trimmed[0]["content"] == "不知道，订单信息里没有家属电话"


def test_guard_chat_text_allows_emergency_numbers() -> None:
    """120 不是「编造的事实」：急症回答里出现它不该被标「数字以订单为准」。"""
    _, warnings = policies.guard_chat_text(
        "老人胸痛请立即拨打120，同时联系站点管家。", facts_text="{}"
    )
    assert policies.CHAT_NUMBER_WARNING not in warnings


def test_guard_chat_text_flags_numbers_not_in_facts() -> None:
    facts_text = json.dumps({"order": {"scheduled_at": "2026-11-26 14:00"}})
    answer, warnings = policies.guard_chat_text(
        "订单时间是 14:00，服务 3 小时。", facts_text=facts_text
    )
    assert answer
    assert policies.CHAT_NUMBER_WARNING in warnings
