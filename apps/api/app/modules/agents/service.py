"""Agent 护栏层：开关、配额、脱敏、审计与错误出口。

这一层在图的**外面**，图里任何节点都绕不过去：
- 开关关闭时直接 503，连工具都不会构造；
- 配额按「当天有模型调用的不同 trace」计数，档案为空的提示不占额度；
- 每条请求写一条汇总审计，模型调用本身由 callback 另写一行。

阶段六在这里补了两个管理端解释场景：事实仍由规则算出，模型只负责解释；
同一订单/任务在 TTL 内且事实未变时直接复用上次结果，不重复付费。

阶段七补了员工「这单助手」：绑定单张订单的多轮窄问答，支持 SSE 逐字输出。
它使用独立额度与独立审计口径（只记字数与意图，不存问题与回答原文）。
"""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session

from ...core.config import settings
from ...core.enums import AgentActionStatus, AgentScenario, Role
from ...core.errors import AppError
from ...core.time import business_today_start_utc, utcnow
from ...db.models import AgentAction, User
from ..audit import AuditService
from ..orders.service import OrderService
from ..tasks.repository import TaskRepository
from ..tasks.service import TaskService
from . import policies, prompts
from .audit import AgentAuditCallback, write_agent_step
from .errors import AgentRateLimitedError, AgentUnavailableError
from .runtime import AgentRuntime
from .schemas import (
    AgentStatusOut,
    ChatOut,
    DispatchAlternativeOut,
    DispatchExcludedOut,
    DispatchRecommendationOut,
    DispatchSuggestOut,
    ExplainActionOut,
    PrepBriefOut,
    RecordDraftOut,
    TaskExplainOut,
)
from .tools import AgentTools

# 汇总行固定排在所有节点之后，同时作为「非模型调用」的标记
SUMMARY_STEP = 90

# 额度按场景分组：员工写记录与对话互不挤占，管理员解释单独一套
_STAFF_WRITE_SCENARIOS = (str(AgentScenario.RECORD_DRAFT), str(AgentScenario.PREP_BRIEF))
_ADMIN_SCENARIOS = (str(AgentScenario.DISPATCH_SUGGEST), str(AgentScenario.TASK_EXPLAIN))
_CHAT_SCENARIOS = (str(AgentScenario.CHAT),)


def _sse(payload: dict[str, Any]) -> str:
    """SSE 单帧：只发 data 行，前端按其中的 ``type`` 字段分派。

    不用 ``event:`` 行：浏览器 EventSource 不支持 POST，前端本就是自己解析流，
    多一层事件名只是多一个可能写错的地方。
    """
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


@dataclass(frozen=True)
class ChatPlan:
    """一次对话请求的前置结果：额度、权限、事实、意图都已确定，只差生成。

    流式接口必须先完成这些再开流：一旦开始推流，状态码已经发出去了，
    429/503 只能用 error 事件收尾，前端体验会差很多。
    """

    user_id: int
    order_id: int
    question: str
    history: list[dict[str, str]]
    facts: dict[str, Any]
    intent: str
    short: tuple[str, str] | None
    trace_id: str
    thread_id: str
    callback: AgentAuditCallback
    started: float


class AgentService:
    def __init__(self, db: Session, orders: OrderService) -> None:
        self._db = db
        self._orders = orders
        self._runtime = AgentRuntime()

    # ------------------------------------------------------------- 状态与护栏
    def status(self, user: User) -> AgentStatusOut:
        limit = settings.agent_daily_limit_per_user
        admin_limit = settings.agent_admin_daily_limit_per_user
        chat_limit = settings.agent_chat_daily_limit_per_user
        # daily_limit/remaining 是「本角色的主额度」：员工看写记录，管理员看解释。
        # 管理员必须用管理端上限，否则会出现「界面显示额度 0、实际还能调 40 次」。
        if user.role == Role.ADMIN:
            main_limit = admin_limit
            used = self._used_today(user.id, _ADMIN_SCENARIOS)
        else:
            main_limit = limit
            used = self._used_today(user.id, _STAFF_WRITE_SCENARIOS)
        admin_used = self._used_today(user.id, _ADMIN_SCENARIOS)
        chat_used = self._used_today(user.id, _CHAT_SCENARIOS)
        # 只有管理员才下发管理端场景：前端据此决定是否渲染「AI 说明 / AI 解释」
        admin_scenarios = (
            [str(AgentScenario.DISPATCH_SUGGEST), str(AgentScenario.TASK_EXPLAIN)]
            if settings.agent_enabled and user.role == Role.ADMIN
            else []
        )
        return AgentStatusOut(
            enabled=settings.agent_enabled,
            provider=settings.llm_provider,
            model=settings.llm_model or "mock",
            daily_limit=main_limit,
            used_today=used,
            remaining=max(0, main_limit - used),
            prep_brief_enabled=settings.agent_enabled,
            admin_scenarios=admin_scenarios,
            admin_daily_limit=admin_limit,
            admin_remaining=max(0, admin_limit - admin_used),
            # 对话入口只给员工：管理端已有解释场景，不重复开一个聊天口
            chat_enabled=settings.agent_enabled and user.role == Role.STAFF,
            chat_daily_limit=chat_limit,
            chat_used_today=chat_used,
            chat_remaining=max(0, chat_limit - chat_used),
        )

    def _used_today(
        self, user_id: int, scenarios: tuple[str, ...] | None = None
    ) -> int:
        """按不同 trace 计数：一次请求命中多个节点也只算一次。

        ``scenarios`` 把「写记录」「对话」「管理端解释」三套额度分开统计；
        传 ``None`` 表示不区分场景。
        """
        stmt = select(func.count(distinct(AgentAction.trace_id))).where(
            AgentAction.user_id == user_id,
            AgentAction.created_at >= business_today_start_utc(),
            AgentAction.step < SUMMARY_STEP,
        )
        if scenarios:
            stmt = stmt.where(AgentAction.scenario.in_(scenarios))
        return int(self._db.scalar(stmt) or 0)

    def _ensure_available(
        self,
        user: User,
        *,
        limit: int | None = None,
        scenarios: tuple[str, ...] | None = None,
    ) -> None:
        """开关与配额检查。

        管理员与对话各走自己的额度：排查或连续追问不应该把员工当天的
        写记录额度吃掉。
        """
        if not settings.agent_enabled:
            raise AgentUnavailableError()
        effective = limit if limit is not None else settings.agent_daily_limit_per_user
        if self._used_today(user.id, scenarios) >= effective:
            raise AgentRateLimitedError()

    # ----------------------------------------------------------------- 场景
    def record_draft(self, user: User, order_id: int, rough_notes: str, photo_count: int):
        self._ensure_available(user, scenarios=_STAFF_WRITE_SCENARIOS)
        trace_id = uuid.uuid4().hex
        scenario = str(AgentScenario.RECORD_DRAFT)
        callback = AgentAuditCallback(
            trace_id=trace_id,
            user_id=user.id,
            scenario=scenario,
            payload={
                "order_id": order_id,
                "photo_count": photo_count,
                "prompt_version": prompts.RECORD_DRAFT_PROMPT_VERSION,
            },
        )
        tools = AgentTools(self._orders, user)
        started = time.perf_counter()
        try:
            result = self._runtime.record_draft(
                tools=tools,
                callback=callback,
                order_id=order_id,
                rough_notes=rough_notes,
                photo_count=photo_count,
            )
        except AppError as exc:
            self._write_summary(trace_id, user.id, scenario, order_id, exc.code, started)
            raise
        except Exception:
            self._write_summary(trace_id, user.id, scenario, order_id, "unexpected", started)
            raise
        self._write_summary(
            trace_id,
            user.id,
            scenario,
            order_id,
            "",
            started,
            extra={
                "output_chars": len(result.content),
                "warnings": result.warnings,
                "prep_items": len(result.prep_brief),
            },
        )
        return RecordDraftOut(
            content=result.content,
            prep_brief=result.prep_brief,
            warnings=result.warnings,
            model=result.model,
            latency_ms=result.latency_ms,
        )

    def prep_brief(self, user: User, order_id: int) -> PrepBriefOut:
        self._ensure_available(user, scenarios=_STAFF_WRITE_SCENARIOS)
        trace_id = uuid.uuid4().hex
        scenario = str(AgentScenario.PREP_BRIEF)
        callback = AgentAuditCallback(
            trace_id=trace_id,
            user_id=user.id,
            scenario=scenario,
            payload={
                "order_id": order_id,
                "prompt_version": prompts.PREP_BRIEF_PROMPT_VERSION,
            },
        )
        tools = AgentTools(self._orders, user)
        started = time.perf_counter()
        try:
            result = self._runtime.prep_brief(
                tools=tools, callback=callback, order_id=order_id
            )
        except AppError as exc:
            self._write_summary(trace_id, user.id, scenario, order_id, exc.code, started)
            raise
        except Exception:
            self._write_summary(trace_id, user.id, scenario, order_id, "unexpected", started)
            raise
        self._write_summary(
            trace_id,
            user.id,
            scenario,
            order_id,
            "",
            started,
            extra={"items": len(result.items), "warnings": result.warnings},
        )
        return PrepBriefOut(
            order_id=order_id,
            items=result.items,
            warnings=result.warnings,
            model=result.model,
            latency_ms=result.latency_ms,
        )

    # ------------------------------------------------------ 管理端解释场景
    def dispatch_suggest(
        self, user: User, order_id: int, *, force_refresh: bool = False
    ) -> DispatchSuggestOut:
        """派单建议解释：人由规则选出，模型只讲道理。

        无候选时不调模型（没有事实可讲）；输出不合格时整单回退到规则文案，
        前端永远有内容可看，不会因为 AI 抖动而阻塞派单。
        """
        self._ensure_available(
            user,
            limit=settings.agent_admin_daily_limit_per_user,
            scenarios=_ADMIN_SCENARIOS,
        )
        tools = AgentTools(self._orders, user)
        facts = tools.dispatch_facts(order_id)
        digest = policies.facts_hash(facts)
        scenario = str(AgentScenario.DISPATCH_SUGGEST)
        thread_id = f"{scenario}:{order_id}"

        cached = None if force_refresh else self._cached(thread_id, digest, scenario=scenario)
        if cached is not None:
            return self._dispatch_out(
                order_id,
                facts,
                cached["output"],
                source="cache",
                warnings=cached["warnings"],
                trace_id=cached["trace_id"],
                model=cached["model"],
                facts_hash=digest,
            )

        rule = self._dispatch_rule_result(facts)
        if not facts.get("candidates"):
            # 无候选：不产生模型调用，只留汇总行，便于统计「无候选」占比
            trace_id = uuid.uuid4().hex
            self._write_summary(
                trace_id,
                user.id,
                scenario,
                order_id,
                "",
                time.perf_counter(),
                extra={"source": "rule", "warnings": ["no_candidates"], "facts_hash": digest},
                thread_id=thread_id,
            )
            return self._dispatch_out(
                order_id,
                facts,
                rule,
                source="rule",
                warnings=["no_candidates"],
                trace_id=trace_id,
                facts_hash=digest,
            )

        trace_id = uuid.uuid4().hex
        callback = AgentAuditCallback(
            trace_id=trace_id,
            user_id=user.id,
            scenario=scenario,
            payload={
                "order_id": order_id,
                "prompt_version": prompts.DISPATCH_SUGGEST_PROMPT_VERSION,
            },
        )
        started = time.perf_counter()
        try:
            result = self._runtime.dispatch_suggest(
                callback=callback, facts=facts, max_tokens=settings.agent_dispatch_max_tokens
            )
        except AppError as exc:
            self._write_summary(
                trace_id, user.id, scenario, order_id, exc.code, started,
                extra={"facts_hash": digest}, thread_id=thread_id,
            )
            raise
        except Exception:
            self._write_summary(
                trace_id, user.id, scenario, order_id, "unexpected", started,
                extra={"facts_hash": digest}, thread_id=thread_id,
            )
            raise

        if result.result.get("staff_id") is None:
            # 护栏拒绝了模型输出：本次调用已花钱，但不把半成品给前端
            source = "rule"
            output = rule
            warnings = [*result.warnings, "fallback_rule"]
        else:
            source = "llm"
            output = result.result
            warnings = list(result.warnings)

        self._write_summary(
            trace_id,
            user.id,
            scenario,
            order_id,
            "",
            started,
            extra={
                "source": source,
                "warnings": warnings,
                "facts_hash": digest,
                "output": output,
                "model": result.model,
            },
            thread_id=thread_id,
            model=result.model,
        )
        return self._dispatch_out(
            order_id,
            facts,
            output,
            source=source,
            warnings=warnings,
            trace_id=trace_id,
            model=result.model,
            latency_ms=result.latency_ms,
            facts_hash=digest,
        )

    def task_explain(
        self, user: User, task_id: int, *, force_refresh: bool = False
    ) -> TaskExplainOut:
        """异常解释：把扫描规则已产出的事实翻成管理员能直接执行的话。

        已处理/已收敛的任务不再调模型：历史解释留在审计里，重复解释没有意义。
        """
        self._ensure_available(
            user,
            limit=settings.agent_admin_daily_limit_per_user,
            scenarios=_ADMIN_SCENARIOS,
        )
        task = self._task_service().get(task_id)
        facts = self._task_facts(task)
        digest = policies.facts_hash(facts)
        scenario = str(AgentScenario.TASK_EXPLAIN)
        thread_id = f"{scenario}:{task_id}"
        rule = self._task_rule_result(task)

        cached = None if force_refresh else self._cached(thread_id, digest, scenario=scenario)
        if cached is not None:
            return self._task_out(
                task,
                cached["output"],
                source="cache",
                warnings=cached["warnings"],
                trace_id=cached["trace_id"],
                model=cached["model"],
                facts_hash=digest,
            )

        if task.status not in ("open", "snoozed"):
            trace_id = uuid.uuid4().hex
            self._write_summary(
                trace_id,
                user.id,
                scenario,
                task.order_id,
                "",
                time.perf_counter(),
                extra={
                    "task_id": task_id,
                    "source": "rule",
                    "warnings": ["task_closed"],
                    "facts_hash": digest,
                },
                thread_id=thread_id,
            )
            return self._task_out(
                task,
                rule,
                source="rule",
                warnings=["task_closed"],
                trace_id=trace_id,
                facts_hash=digest,
            )

        trace_id = uuid.uuid4().hex
        callback = AgentAuditCallback(
            trace_id=trace_id,
            user_id=user.id,
            scenario=scenario,
            payload={
                "task_id": task_id,
                "prompt_version": prompts.TASK_EXPLAIN_PROMPT_VERSION,
            },
        )
        started = time.perf_counter()
        try:
            result = self._runtime.task_explain(
                callback=callback, facts=facts, max_tokens=settings.agent_task_max_tokens
            )
        except AppError as exc:
            self._write_summary(
                trace_id, user.id, scenario, task.order_id, exc.code, started,
                extra={"task_id": task_id, "facts_hash": digest}, thread_id=thread_id,
            )
            raise
        except Exception:
            self._write_summary(
                trace_id, user.id, scenario, task.order_id, "unexpected", started,
                extra={"task_id": task_id, "facts_hash": digest}, thread_id=thread_id,
            )
            raise

        if not result.result.get("what_happened"):
            source = "rule"
            output = rule
            warnings = [*result.warnings, "fallback_rule"]
        else:
            source = "llm"
            output = result.result
            warnings = list(result.warnings)

        self._write_summary(
            trace_id,
            user.id,
            scenario,
            task.order_id,
            "",
            started,
            extra={
                "task_id": task_id,
                "source": source,
                "warnings": warnings,
                "facts_hash": digest,
                "output": output,
                "model": result.model,
            },
            thread_id=thread_id,
            model=result.model,
        )
        return self._task_out(
            task,
            output,
            source=source,
            warnings=warnings,
            trace_id=trace_id,
            model=result.model,
            latency_ms=result.latency_ms,
            facts_hash=digest,
        )

    # ------------------------------------------------------------- 解释辅助
    def _cached(
        self, thread_id: str, digest: str, *, scenario: str
    ) -> dict[str, Any] | None:
        """取同场景、同主体、同事实指纹且未过期的上次结果；事实变了自然不命中。

        除了 ``thread_id``（已经带场景前缀），再显式按 ``scenario`` 过滤一道：
        所有解释与对话共用一张审计表，只看键名约定是结构脆弱点。
        """
        if settings.agent_cache_ttl_seconds <= 0:
            return None
        since = utcnow() - timedelta(seconds=settings.agent_cache_ttl_seconds)
        stmt = (
            select(AgentAction)
            .where(
                AgentAction.thread_id == thread_id,
                AgentAction.scenario == scenario,
                AgentAction.step == SUMMARY_STEP,
                AgentAction.created_at >= since,
            )
            .order_by(AgentAction.id.desc())
            .limit(5)
        )
        for row in self._db.scalars(stmt):
            payload = dict(row.payload or {})
            output = payload.get("output")
            if payload.get("facts_hash") != digest or not isinstance(output, dict) or not output:
                continue
            return {
                "output": output,
                "warnings": list(payload.get("warnings") or []),
                "model": str(payload.get("model") or row.model or ""),
                "trace_id": row.trace_id,
            }
        return None

    def _dispatch_rule_result(self, facts: dict[str, Any]) -> dict[str, Any]:
        """规则版解释：模型不可用时的降级文案，内容全部来自候选引擎。"""
        candidates = facts.get("candidates") or []
        gaps = list(facts.get("data_gaps") or [])
        if not candidates:
            excluded = facts.get("excluded") or []
            reasons = [
                f"{item.get('name', '')}：{'；'.join(item.get('reasons') or [])}"
                for item in excluded[:2]
            ]
            return {
                "staff_id": None,
                "summary": "规则未找到可用候选，请人工协调",
                "why": [],
                "risks": reasons,
                "data_gaps": gaps,
                "alternatives": [],
            }

        top = candidates[0]
        alternatives = []
        for item in candidates[1:3]:
            note = ""
            if item.get("risks"):
                note = str(item["risks"][0])
            elif item.get("reasons"):
                note = str(item["reasons"][0])
            alternatives.append(
                {
                    "staff_id": item["staff_id"],
                    "name": item.get("name", ""),
                    "note": note[:25],
                }
            )
        return {
            "staff_id": top["staff_id"],
            "summary": f"规则推荐 {top.get('name', '')}（{top.get('score', 0)} 分）",
            "why": [str(item)[:40] for item in (top.get("reasons") or [])][:3],
            "risks": [str(item)[:40] for item in (top.get("risks") or [])][:3],
            "data_gaps": gaps,
            "alternatives": alternatives,
        }

    def _dispatch_out(
        self,
        order_id: int,
        facts: dict[str, Any],
        output: dict[str, Any],
        *,
        source: str,
        warnings: list[str],
        trace_id: str,
        model: str = "",
        latency_ms: int = 0,
        facts_hash: str = "",
    ) -> DispatchSuggestOut:
        """组装响应：推荐人始终取规则第一名，不看模型返回的 staff_id。"""
        candidates = facts.get("candidates") or []
        by_id = {int(item["staff_id"]): item for item in candidates}
        recommendation = None
        if candidates:
            top = candidates[0]
            recommendation = DispatchRecommendationOut(
                staff_id=int(top["staff_id"]),
                name=str(top.get("name") or ""),
                score=int(top.get("score") or 0),
            )

        alternatives: list[DispatchAlternativeOut] = []
        for item in output.get("alternatives") or []:
            try:
                staff_id = int(item.get("staff_id"))
            except (TypeError, ValueError):
                continue
            if staff_id not in by_id:
                continue
            alternatives.append(
                DispatchAlternativeOut(
                    staff_id=staff_id,
                    name=str(by_id[staff_id].get("name") or ""),
                    note=str(item.get("note") or ""),
                )
            )

        return DispatchSuggestOut(
            order_id=order_id,
            recommendation=recommendation,
            summary=str(output.get("summary") or ""),
            why=[str(item) for item in output.get("why") or []],
            risks=[str(item) for item in output.get("risks") or []],
            data_gaps=[str(item) for item in facts.get("data_gaps") or []],
            alternatives=alternatives,
            excluded=[
                DispatchExcludedOut(
                    name=str(item.get("name") or ""),
                    reasons=[str(reason) for reason in item.get("reasons") or []],
                )
                for item in facts.get("excluded") or []
            ],
            source=source,  # type: ignore[arg-type]
            warnings=list(warnings),
            trace_id=trace_id,
            model=model,
            latency_ms=latency_ms,
            facts_hash=facts_hash,
            generated_at=utcnow(),
        )

    def _task_service(self) -> TaskService:
        """只读场景：临时构造任务服务，复用其权限与 DTO，不另写一套查询。"""
        return TaskService(self._db, TaskRepository(self._db), AuditService(self._db))

    def _task_facts(self, task: Any) -> dict[str, Any]:
        """任务事实：直接用扫描规则写好的 detail，不重新查订单。"""
        detail = dict(task.detail or {})
        return {
            "task": {
                "type": task.type,
                "severity": task.severity,
                "status": task.status,
                "title": task.title,
                "order_no": task.order_no,
                "service": task.service_name,
                "station": task.station_name,
                "elder_name": task.elder_name,
                "scheduled_at": (
                    task.scheduled_at.strftime("%Y-%m-%d %H:%M") if task.scheduled_at else ""
                ),
                "order_status": task.order_status,
            },
            "detail": {
                "rule": str(detail.get("rule") or ""),
                "why": str(detail.get("why") or ""),
                "suggest": str(detail.get("suggest") or ""),
                "elapsed_minutes": int(detail.get("elapsed_minutes") or 0),
                "threshold_minutes": int(detail.get("threshold_minutes") or 0),
                # 扫描规则里的 facts 是嵌套字典，统一递归脱敏后再交给模型
                "facts": policies.scrub_tree(detail.get("facts") or {}),
            },
        }

    def _task_rule_result(self, task: Any) -> dict[str, Any]:
        """规则版解释：直接复用扫描规则写好的 why / suggest。"""
        detail = dict(task.detail or {})
        why = str(detail.get("why") or task.title or "")
        suggest = str(detail.get("suggest") or "")[:20]
        return {
            "what_happened": why,
            "why": why,
            "next_actions": [
                {
                    "action": "manual_check",
                    "label": suggest or policies.ALLOWED_TASK_ACTIONS["manual_check"],
                }
            ],
            "escalate": task.severity == "high",
            "data_gaps": [],
        }

    def _task_out(
        self,
        task: Any,
        output: dict[str, Any],
        *,
        source: str,
        warnings: list[str],
        trace_id: str,
        model: str = "",
        latency_ms: int = 0,
        facts_hash: str = "",
    ) -> TaskExplainOut:
        """组装响应：动作只认白名单，模型写了不存在的动作直接丢弃。"""
        actions: list[ExplainActionOut] = []
        for item in output.get("next_actions") or []:
            action = str(item.get("action") or "")
            if action not in policies.ALLOWED_TASK_ACTIONS:
                continue
            actions.append(
                ExplainActionOut(
                    action=action,
                    label=str(item.get("label") or policies.ALLOWED_TASK_ACTIONS[action]),
                )
            )
        if not actions:
            actions = [
                ExplainActionOut(
                    action="manual_check",
                    label=policies.ALLOWED_TASK_ACTIONS["manual_check"],
                )
            ]

        return TaskExplainOut(
            task_id=task.id,
            type=task.type,
            title=task.title,
            what_happened=str(output.get("what_happened") or ""),
            why=str(output.get("why") or ""),
            next_actions=actions,
            escalate=bool(output.get("escalate")),
            data_gaps=[str(item) for item in output.get("data_gaps") or []],
            source=source,  # type: ignore[arg-type]
            warnings=list(warnings),
            trace_id=trace_id,
            model=model,
            latency_ms=latency_ms,
            facts_hash=facts_hash,
            generated_at=utcnow(),
        )

    # ------------------------------------------------------ 员工「这单助手」
    def prepare_chat(
        self, user: User, order_id: int, question: str, history: list[dict[str, Any]]
    ) -> ChatPlan:
        """对话前置：额度、权限、事实、意图一次算完。

        流式接口必须先走完这一步：一开流，403/429/503 就只能用 error 事件收尾了。

        顺序有讲究：先判开关，再算急症/越界短路，最后才查额度与订单。
        否则额度用尽时连「胸痛怎么办」都只能回 429，安全指引被运营配置卡死。
        """
        if not settings.agent_enabled:
            raise AgentUnavailableError()
        short = policies.chat_short_circuit(question)
        if short is None:
            self._ensure_available(
                user,
                limit=settings.agent_chat_daily_limit_per_user,
                scenarios=_CHAT_SCENARIOS,
            )
            # 权限与订单状态在这一步校验，非本人订单直接 403，不在可问区间的直接 409
            facts = AgentTools(self._orders, user).chat_facts(order_id)
        else:
            # 固定回答不需要任何订单事实，也就不去碰别人的单
            facts = {}
        trimmed = policies.trim_chat_history(
            history,
            max_messages=settings.agent_chat_history_turns,
            max_chars=settings.agent_chat_message_max_chars,
        )
        intent = policies.classify_chat_intent(question)
        trace_id = uuid.uuid4().hex
        scenario = str(AgentScenario.CHAT)
        return ChatPlan(
            user_id=user.id,
            order_id=order_id,
            question=question,
            history=trimmed,
            facts=facts,
            intent=intent,
            short=short,
            trace_id=trace_id,
            # 同一订单的问答可以串起来排查，但对话不进缓存（上下文每次都不同）
            thread_id=f"{scenario}:{order_id}",
            callback=AgentAuditCallback(
                trace_id=trace_id,
                user_id=user.id,
                scenario=scenario,
                # 只记问题字数与意图：问题原文里可能有老人姓名与病情
                payload={
                    "order_id": order_id,
                    "intent": intent,
                    "question_chars": len(question),
                    "prompt_version": prompts.CHAT_PROMPT_VERSION,
                },
            ),
            started=time.perf_counter(),
        )

    def chat(
        self, user: User, order_id: int, question: str, history: list[dict[str, Any]]
    ) -> ChatOut:
        """非流式回答：供联调与不支持 SSE 的客户端使用。"""
        plan = self.prepare_chat(user, order_id, question, history)
        if plan.short is not None:
            code, reply = plan.short
            self._write_chat_summary(plan, reply, source="rule", warnings=[code])
            return self._chat_out(plan, reply, source="rule", warnings=[code])

        try:
            result = self._runtime.chat(
                callback=plan.callback,
                facts=plan.facts,
                question=plan.question,
                history=plan.history,
                max_tokens=settings.agent_chat_max_tokens,
            )
        except AppError as exc:
            self._write_chat_summary(plan, "", source="rule", warnings=[], error_code=exc.code)
            raise
        except Exception:
            self._write_chat_summary(
                plan, "", source="rule", warnings=[], error_code="unexpected"
            )
            raise

        self._write_chat_summary(
            plan, result.answer, source="llm", warnings=result.warnings, model=result.model
        )
        return self._chat_out(
            plan,
            result.answer,
            source="llm",
            warnings=result.warnings,
            model=result.model,
            latency_ms=result.latency_ms,
        )

    def chat_stream(self, plan: ChatPlan) -> Iterator[str]:
        """SSE 逐帧输出：meta → delta* → done；开流后的错误走 error 事件。

        中途断开也要留审计（``client_closed``）：否则「只答了一半」在数据上
        会表现为成功，成本与可用率都会被高估。
        """
        yield _sse(
            {
                "type": "meta",
                "trace_id": plan.trace_id,
                "order_id": plan.order_id,
                "intent": plan.intent,
                "source": "rule" if plan.short is not None else "llm",
            }
        )
        answer = ""
        emitted: list[str] = []
        warnings: list[str] = []
        model = ""
        try:
            if plan.short is not None:
                code, reply = plan.short
                warnings = [code]
                answer = reply
                yield _sse({"type": "delta", "text": reply})
            else:
                session = self._runtime.chat_stream(
                    callback=plan.callback,
                    facts=plan.facts,
                    question=plan.question,
                    history=plan.history,
                    max_tokens=settings.agent_chat_max_tokens,
                )
                for piece in session:
                    # 自己再记一份：异常中断时 session.answer 还没赋上，
                    # 只看它会把「已发出几百字」记成 0 字
                    emitted.append(piece)
                    yield _sse({"type": "delta", "text": piece})
                answer = session.answer or "".join(emitted)
                warnings = list(session.warnings)
                model = self._runtime.model_name
        except GeneratorExit:
            # 客户端断开：不写 done 帧，但审计要把已发出的字数记下来
            self._write_chat_summary(
                plan, answer or "".join(emitted), source="llm", warnings=warnings,
                model=model, error_code="client_closed",
            )
            raise
        except AppError as exc:
            self._write_chat_summary(
                plan, answer or "".join(emitted), source="llm", warnings=warnings,
                model=model, error_code=exc.code,
            )
            yield _sse({"type": "error", "code": exc.code, "message": exc.message})
            return
        except Exception:  # noqa: BLE001 - 已开流，只能把未知错误翻译成 error 事件
            self._write_chat_summary(
                plan, answer or "".join(emitted), source="llm", warnings=warnings,
                model=model, error_code="unexpected",
            )
            yield _sse(
                {
                    "type": "error",
                    "code": "agent_unavailable",
                    "message": "AI 服务暂时不可用，可先看订单信息或联系站点管家",
                }
            )
            return

        self._write_chat_summary(
            plan, answer, source="llm" if plan.short is None else "rule",
            warnings=warnings, model=model,
        )
        yield _sse(self._chat_done(plan, answer, warnings=warnings))

    def _chat_done(
        self, plan: ChatPlan, answer: str, *, warnings: list[str]
    ) -> dict[str, Any]:
        """done 帧：前端用它拿最终文本与提示，也能校正流式拼接的尾部误差。"""
        chat_limit = settings.agent_chat_daily_limit_per_user
        used = self._used_today(plan.user_id, _CHAT_SCENARIOS)
        return {
            "type": "done",
            "order_id": plan.order_id,
            "answer": answer,
            "intent": plan.intent,
            "source": "rule" if plan.short is not None else "llm",
            "warnings": list(warnings),
            "trace_id": plan.trace_id,
            "remaining": max(0, chat_limit - used),
        }

    def _chat_out(
        self,
        plan: ChatPlan,
        answer: str,
        *,
        source: str,
        warnings: list[str],
        model: str = "",
        latency_ms: int = 0,
    ) -> ChatOut:
        chat_limit = settings.agent_chat_daily_limit_per_user
        used = self._used_today(plan.user_id, _CHAT_SCENARIOS)
        return ChatOut(
            order_id=plan.order_id,
            answer=answer,
            intent=plan.intent,
            warnings=list(warnings),
            source=source,  # type: ignore[arg-type]
            trace_id=plan.trace_id,
            model=model,
            latency_ms=latency_ms,
            remaining=max(0, chat_limit - used),
        )

    def _write_chat_summary(
        self,
        plan: ChatPlan,
        answer: str,
        *,
        source: str,
        warnings: list[str],
        model: str = "",
        error_code: str = "",
    ) -> None:
        """对话汇总行：只记字数与意图，不存问题与回答原文。

        不写 ``output`` / ``facts_hash``：万一将来有人把 ``_cached`` 用在对话上，
        也不会把上一轮的问答当成这一轮的事实解释。
        """
        self._write_summary(
            plan.trace_id,
            plan.user_id,
            str(AgentScenario.CHAT),
            plan.order_id,
            error_code,
            plan.started,
            extra={
                "intent": plan.intent,
                "source": source,
                "answer_chars": len(answer),
                "warnings": list(warnings),
            },
            thread_id=plan.thread_id,
            model=model,
        )

    # ----------------------------------------------------------------- 审计
    def _write_summary(
        self,
        trace_id: str,
        user_id: int,
        scenario: str,
        order_id: int,
        error_code: str,
        started: float,
        extra: dict[str, Any] | None = None,
        *,
        thread_id: str | None = None,
        model: str = "",
    ) -> None:
        """请求级汇总行：失败也要写，前端与运维据此统计可用率。

        ``thread_id`` 同时充当解释场景的缓存键（``scenario:subject``），
        ``payload.output`` 存最后一次合格结果，TTL 内直接复用。
        """
        payload: dict[str, Any] = {"order_id": order_id, **(extra or {})}
        write_agent_step(
            trace_id=trace_id,
            user_id=user_id,
            scenario=scenario,
            step=SUMMARY_STEP,
            status=AgentActionStatus.FAILED if error_code else AgentActionStatus.OK,
            model=model,
            latency_ms=int((time.perf_counter() - started) * 1000),
            error_code=error_code,
            payload=payload,
            thread_id=thread_id,
        )
