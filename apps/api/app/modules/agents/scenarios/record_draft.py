"""单轮图：服务记录代写。

形状刻意保持最小（load → draft → parse），为的是和阶段七的多节点图共用同一个
运行时而不用改结构。所有写操作都在图外，图只产出文本。
"""

from __future__ import annotations

from typing import TypedDict

from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.graph import END, START, StateGraph

from .. import policies, prompts
from ..tools import AgentTools


class RecordState(TypedDict, total=False):
    facts: dict
    redline: bool
    raw: str
    content: str
    prep_brief: list[str]
    warnings: list[str]


def build_record_draft_graph(
    *,
    model: BaseChatModel,
    tools: AgentTools,
    callback,
    order_id: int,
    rough_notes: str,
    photo_count: int,
):
    """构造并编译图。

    节点闭包持有本次请求的参数：``State`` 只放中间结果，不把用户输入塞进图状态，
    避免将来接 checkpointer 时把原文持久化。
    """

    def load(state: RecordState) -> RecordState:
        # 事实与权限校验都在工具层完成；图内拿到的是已脱敏的字典
        facts = tools.order_facts(order_id, for_record=True, photo_count=photo_count)
        return {
            "facts": facts.to_prompt_dict(),
            "redline": policies.hit_redline(rough_notes),
        }

    def redline(state: RecordState) -> RecordState:
        # 急症场景完全不调模型：固定指引比任何生成结果都可靠
        return {
            "content": policies.REDLINE_REPLY,
            "prep_brief": [],
            "warnings": [policies.REDLINE_WARNING],
        }

    def draft(state: RecordState) -> RecordState:
        messages = prompts.record_draft_messages(
            state["facts"], rough_notes, photo_count
        )
        response = model.invoke(messages, config={"callbacks": [callback]})
        return {"raw": response.content}

    def parse(state: RecordState) -> RecordState:
        payload = policies.parse_json_object(state.get("raw", ""))
        content, prep_brief, warnings = policies.guard_record_output(payload)
        return {"content": content, "prep_brief": prep_brief, "warnings": warnings}

    def route(state: RecordState) -> str:
        return "redline" if state.get("redline") else "draft"

    graph = StateGraph(RecordState)
    graph.add_node("load", load)
    graph.add_node("redline", redline)
    graph.add_node("draft", draft)
    graph.add_node("parse", parse)

    graph.add_edge(START, "load")
    graph.add_conditional_edges("load", route, {"redline": "redline", "draft": "draft"})
    graph.add_edge("draft", "parse")
    graph.add_edge("redline", END)
    graph.add_edge("parse", END)
    return graph.compile()
