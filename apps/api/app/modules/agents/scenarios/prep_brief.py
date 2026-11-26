"""单轮图：服务前提示。

档案为空时直接短路（``empty`` 节点），不产生模型调用：
「没有问题可提示」不应该花一次 token 去问模型。
"""

from __future__ import annotations

from typing import TypedDict

from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.graph import END, START, StateGraph

from ....core.config import settings
from .. import policies, prompts
from ..tools import AgentTools


class PrepState(TypedDict, total=False):
    facts: dict
    has_health_info: bool
    raw: str
    items: list[str]
    warnings: list[str]


def build_prep_brief_graph(
    *,
    model: BaseChatModel,
    tools: AgentTools,
    callback,
    order_id: int,
):
    def load(state: PrepState) -> PrepState:
        facts = tools.order_facts(order_id, for_record=False)
        return {
            "facts": facts.to_prompt_dict(),
            "has_health_info": facts.has_health_info,
        }

    def empty(state: PrepState) -> PrepState:
        return {"items": [], "warnings": []}

    def brief(state: PrepState) -> PrepState:
        messages = prompts.prep_brief_messages(state["facts"])
        # 提示条数很少，单独的 token 上限避免按记录草稿的额度付费
        response = model.invoke(
            messages,
            max_tokens=settings.agent_prep_max_tokens,
            config={"callbacks": [callback]},
        )
        return {"raw": response.content}

    def parse(state: PrepState) -> PrepState:
        payload = policies.parse_json_object(state.get("raw", ""))
        items, warnings = policies.guard_prep_output(payload)
        return {"items": items, "warnings": warnings}

    def route(state: PrepState) -> str:
        return "brief" if state.get("has_health_info") else "empty"

    graph = StateGraph(PrepState)
    graph.add_node("load", load)
    graph.add_node("empty", empty)
    graph.add_node("brief", brief)
    graph.add_node("parse", parse)

    graph.add_edge(START, "load")
    graph.add_conditional_edges("load", route, {"brief": "brief", "empty": "empty"})
    graph.add_edge("brief", "parse")
    graph.add_edge("parse", END)
    graph.add_edge("empty", END)
    return graph.compile()
