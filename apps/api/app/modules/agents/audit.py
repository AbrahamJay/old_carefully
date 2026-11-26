"""Agent 审计：把每次模型调用落成 ``agent_actions`` 一行。

为什么用独立会话：审计必须在业务失败（超时、5xx、回滚）时依然留存，
否则「AI 可用率」会被系统性高估。因此这里不参与请求事务，
每条审计独立短事务提交，失败只记日志、不影响主流程。

白名单原则：只记录订单号、模型、耗时、token 数、输入摘要（SHA-256），
用户输入与老人健康信息一律不落库。
"""

from __future__ import annotations

import hashlib
import logging
import time
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult

from ...core.enums import AgentActionStatus
from ...db.models import AgentAction
from ...db.session import SessionLocal

logger = logging.getLogger(__name__)


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def write_agent_step(
    *,
    trace_id: str,
    user_id: int,
    scenario: str,
    step: int,
    status: str,
    model: str = "",
    latency_ms: int = 0,
    tokens_in: int = 0,
    tokens_out: int = 0,
    error_code: str = "",
    payload: dict[str, Any] | None = None,
    payload_digest: str = "",
    thread_id: str | None = None,
) -> None:
    """写一条审计；失败只记日志，绝不把异常抛回业务流程。"""
    try:
        with SessionLocal() as db:
            db.add(
                AgentAction(
                    trace_id=trace_id,
                    thread_id=thread_id,
                    user_id=user_id,
                    scenario=scenario,
                    step=step,
                    status=status,
                    model=model[:60],
                    latency_ms=latency_ms,
                    tokens_in=tokens_in,
                    tokens_out=tokens_out,
                    error_code=error_code[:40],
                    payload=payload or {},
                    payload_digest=payload_digest,
                )
            )
            db.commit()
    except Exception as exc:  # noqa: BLE001 - 审计失败不能影响主流程
        logger.warning("写入 agent_actions 失败：%s", exc)


class AgentAuditCallback(BaseCallbackHandler):
    """LangChain 回调：模型调用开始/结束/异常各对应一条审计。

    单轮场景每次请求只有 1 次模型调用；阶段七的图有多个节点时，
    同一 ``trace_id`` 会自然产生多行，``step`` 递增，无需改表。
    """

    def __init__(
        self,
        *,
        trace_id: str,
        user_id: int,
        scenario: str,
        payload: dict[str, Any] | None = None,
        thread_id: str | None = None,
    ) -> None:
        self._trace_id = trace_id
        self._user_id = user_id
        self._scenario = scenario
        self._payload = payload or {}
        self._thread_id = thread_id
        self._started: dict[str, float] = {}
        self._step = 0
        self._last_digest = ""
        self._last_prompt_chars = 0

    def _next_step(self) -> int:
        step = self._step
        self._step += 1
        return step

    def on_llm_start(self, serialized: dict[str, Any], prompts: list[str], **kwargs: Any) -> None:
        run_id = str(kwargs.get("run_id") or len(self._started))
        self._started[run_id] = time.perf_counter()
        # 只留摘要：可用于排查「同一输入是否重复调用」，又不保存原文
        self._last_digest = _digest("\n".join(prompts))
        self._last_prompt_chars = len("\n".join(prompts))

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        run_id = str(kwargs.get("run_id") or "")
        started = self._started.pop(run_id, None)
        latency_ms = int((time.perf_counter() - started) * 1000) if started else 0
        output = response.llm_output or {}
        write_agent_step(
            trace_id=self._trace_id,
            user_id=self._user_id,
            scenario=self._scenario,
            step=self._next_step(),
            status=AgentActionStatus.OK,
            model=str(output.get("model", "")),
            latency_ms=int(output.get("latency_ms") or latency_ms),
            tokens_in=int(output.get("tokens_in") or 0),
            tokens_out=int(output.get("tokens_out") or 0),
            payload={**self._payload, "prompt_chars": self._last_prompt_chars},
            payload_digest=self._last_digest,
            thread_id=self._thread_id,
        )

    def on_llm_error(self, error: BaseException, **kwargs: Any) -> None:
        run_id = str(kwargs.get("run_id") or "")
        started = self._started.pop(run_id, None)
        latency_ms = int((time.perf_counter() - started) * 1000) if started else 0
        code = getattr(error, "code", error.__class__.__name__)
        write_agent_step(
            trace_id=self._trace_id,
            user_id=self._user_id,
            scenario=self._scenario,
            step=self._next_step(),
            status=AgentActionStatus.FAILED,
            latency_ms=latency_ms,
            error_code=str(code),
            payload=self._payload,
            payload_digest=self._last_digest,
            thread_id=self._thread_id,
        )
