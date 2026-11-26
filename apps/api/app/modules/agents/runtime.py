"""Agent 运行时：图编排的唯一入口。

阶段五登记两张员工端单轮图，阶段六补两张管理端解释图，阶段七补「这单助手」
对话：JSON 路径走图，SSE 路径走 ``ChatStreamSession``（图的 invoke 拿不到增量 token）。
``AgentService`` 与路由不需要感知「这次是图还是生成器」。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel

from .models import build_chat_model
from .scenarios.chat import ChatStreamSession, build_chat_graph
from .scenarios.dispatch_suggest import build_dispatch_suggest_graph
from .scenarios.prep_brief import build_prep_brief_graph
from .scenarios.record_draft import build_record_draft_graph
from .scenarios.task_explain import build_task_explain_graph
from .tools import AgentTools


@dataclass(frozen=True)
class RecordDraftResult:
    content: str
    prep_brief: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    model: str = ""
    latency_ms: int = 0


@dataclass(frozen=True)
class PrepBriefResult:
    items: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    model: str = ""
    latency_ms: int = 0


@dataclass(frozen=True)
class DispatchSuggestResult:
    """管理端派单解释结果；``result`` 为空字典表示护栏拒绝了整份输出。"""

    result: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    model: str = ""
    latency_ms: int = 0


@dataclass(frozen=True)
class TaskExplainResult:
    result: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    model: str = ""
    latency_ms: int = 0


@dataclass(frozen=True)
class ChatResult:
    """「这单助手」的非流式结果；流式由 ``ChatStreamSession`` 自己带着结果。"""

    answer: str = ""
    warnings: list[str] = field(default_factory=list)
    model: str = ""
    latency_ms: int = 0


class AgentRuntime:
    def __init__(self, model: BaseChatModel | None = None) -> None:
        self._model = model or build_chat_model()

    @property
    def model_name(self) -> str:
        return str(getattr(self._model, "model_name", "") or "")

    def record_draft(
        self,
        *,
        tools: AgentTools,
        callback: Any,
        order_id: int,
        rough_notes: str,
        photo_count: int,
    ) -> RecordDraftResult:
        graph = build_record_draft_graph(
            model=self._model,
            tools=tools,
            callback=callback,
            order_id=order_id,
            rough_notes=rough_notes,
            photo_count=photo_count,
        )
        started = time.perf_counter()
        state = graph.invoke({})
        latency_ms = int((time.perf_counter() - started) * 1000)
        return RecordDraftResult(
            content=state.get("content", ""),
            prep_brief=list(state.get("prep_brief") or []),
            warnings=list(state.get("warnings") or []),
            model=self.model_name,
            latency_ms=latency_ms,
        )

    def prep_brief(
        self, *, tools: AgentTools, callback: Any, order_id: int
    ) -> PrepBriefResult:
        graph = build_prep_brief_graph(
            model=self._model, tools=tools, callback=callback, order_id=order_id
        )
        started = time.perf_counter()
        state = graph.invoke({})
        latency_ms = int((time.perf_counter() - started) * 1000)
        return PrepBriefResult(
            items=list(state.get("items") or []),
            warnings=list(state.get("warnings") or []),
            model=self.model_name,
            latency_ms=latency_ms,
        )

    def dispatch_suggest(
        self, *, callback: Any, facts: dict, max_tokens: int
    ) -> DispatchSuggestResult:
        """派单解释：事实已由服务层算好，图内只调一次模型。"""
        graph = build_dispatch_suggest_graph(
            model=self._model, callback=callback, facts=facts, max_tokens=max_tokens
        )
        started = time.perf_counter()
        state = graph.invoke({})
        latency_ms = int((time.perf_counter() - started) * 1000)
        return DispatchSuggestResult(
            result=dict(state.get("result") or {}),
            warnings=list(state.get("warnings") or []),
            model=self.model_name,
            latency_ms=latency_ms,
        )

    def task_explain(
        self, *, callback: Any, facts: dict, max_tokens: int
    ) -> TaskExplainResult:
        """异常解释：事实取自扫描规则已落库的 detail。"""
        graph = build_task_explain_graph(
            model=self._model, callback=callback, facts=facts, max_tokens=max_tokens
        )
        started = time.perf_counter()
        state = graph.invoke({})
        latency_ms = int((time.perf_counter() - started) * 1000)
        return TaskExplainResult(
            result=dict(state.get("result") or {}),
            warnings=list(state.get("warnings") or []),
            model=self.model_name,
            latency_ms=latency_ms,
        )

    # --------------------------------------------------------- 阶段七对话
    def chat(
        self,
        *,
        callback: Any,
        facts: dict,
        question: str,
        history: list[dict[str, str]],
        max_tokens: int,
    ) -> ChatResult:
        """非流式回答：与流式共用 prompt 与护栏，供不支持 SSE 的客户端使用。"""
        graph = build_chat_graph(
            model=self._model,
            callback=callback,
            facts=facts,
            question=question,
            history=history,
            max_tokens=max_tokens,
        )
        started = time.perf_counter()
        state = graph.invoke({})
        latency_ms = int((time.perf_counter() - started) * 1000)
        return ChatResult(
            answer=state.get("answer", ""),
            warnings=list(state.get("warnings") or []),
            model=self.model_name,
            latency_ms=latency_ms,
        )

    def chat_stream(
        self,
        *,
        callback: Any,
        facts: dict,
        question: str,
        history: list[dict[str, str]],
        max_tokens: int,
    ) -> ChatStreamSession:
        """流式回答：返回可迭代会话，迭代结束后从 ``answer`` 取完整文本。"""
        return ChatStreamSession(
            model=self._model,
            callback=callback,
            facts=facts,
            question=question,
            history=history,
            max_tokens=max_tokens,
        )
