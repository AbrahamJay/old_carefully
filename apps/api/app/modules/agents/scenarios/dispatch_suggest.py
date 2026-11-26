"""单轮图：派单建议解释。

人由规则引擎选定（见 ``orders/candidates.py``），这张图只做两件事：
把候选事实交给模型讲成人话，再用护栏把模型可能越界的部分剪掉。

无候选时直接走 ``empty``：没有事实可解释，问模型只会换来一段编造。
"""

from __future__ import annotations

import json
from typing import TypedDict

from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.graph import END, START, StateGraph

from .. import policies, prompts


class DispatchState(TypedDict, total=False):
    facts: dict
    has_candidates: bool
    raw: str
    result: dict
    warnings: list[str]


def build_dispatch_suggest_graph(
    *,
    model: BaseChatModel,
    callback,
    facts: dict,
    max_tokens: int,
):
    """构造并编译图。

    ``facts`` 由服务层预先算好（缓存指纹也用它），图内不再查库，
    这样「能否复用上次结果」与「本次生成」用的是同一份事实。
    """

    def load(state: DispatchState) -> DispatchState:
        return {"facts": facts, "has_candidates": bool(facts.get("candidates"))}

    def empty(state: DispatchState) -> DispatchState:
        return {"result": {}, "warnings": []}

    def explain(state: DispatchState) -> DispatchState:
        messages = prompts.dispatch_suggest_messages(state["facts"])
        response = model.invoke(
            messages,
            max_tokens=max_tokens,
            config={"callbacks": [callback]},
        )
        return {"raw": response.content}

    def parse(state: DispatchState) -> DispatchState:
        payload = policies.parse_json_object(state.get("raw", ""))
        # 事实重新序列化一份给护栏做数字比对：解释里出现的数字必须能在事实里找到
        facts_text = json.dumps(state["facts"], ensure_ascii=False, sort_keys=True, default=str)
        result, warnings = policies.guard_dispatch_output(
            payload,
            candidates=list(state["facts"].get("candidates") or []),
            rule_gaps=list(state["facts"].get("data_gaps") or []),
            facts_text=facts_text,
        )
        return {"result": result, "warnings": warnings}

    def route(state: DispatchState) -> str:
        return "explain" if state.get("has_candidates") else "empty"

    graph = StateGraph(DispatchState)
    graph.add_node("load", load)
    graph.add_node("empty", empty)
    graph.add_node("explain", explain)
    graph.add_node("parse", parse)

    graph.add_edge(START, "load")
    graph.add_conditional_edges("load", route, {"explain": "explain", "empty": "empty"})
    graph.add_edge("explain", "parse")
    graph.add_edge("empty", END)
    graph.add_edge("parse", END)
    return graph.compile()
