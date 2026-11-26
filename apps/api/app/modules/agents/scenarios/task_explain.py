"""单轮图：异常解释。

事实全部来自扫描规则已经写好的 ``admin_tasks.detail``，图内不重新查订单：
规则已经算过阈值与耗时，模型再算一遍只会引入第二套口径。

动作走白名单（``policies.ALLOWED_TASK_ACTIONS``），模型不能发明系统没有的按钮。
"""

from __future__ import annotations

import json
from typing import TypedDict

from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.graph import END, START, StateGraph

from .. import policies, prompts


class TaskExplainState(TypedDict, total=False):
    facts: dict
    raw: str
    result: dict
    warnings: list[str]


def build_task_explain_graph(
    *,
    model: BaseChatModel,
    callback,
    facts: dict,
    max_tokens: int,
):
    """构造并编译图；``facts`` 由服务层从任务详情组装并脱敏。"""

    def load(state: TaskExplainState) -> TaskExplainState:
        return {"facts": facts}

    def explain(state: TaskExplainState) -> TaskExplainState:
        messages = prompts.task_explain_messages(state["facts"])
        response = model.invoke(
            messages,
            max_tokens=max_tokens,
            config={"callbacks": [callback]},
        )
        return {"raw": response.content}

    def parse(state: TaskExplainState) -> TaskExplainState:
        payload = policies.parse_json_object(state.get("raw", ""))
        detail = state["facts"].get("detail") or {}
        facts_text = json.dumps(state["facts"], ensure_ascii=False, sort_keys=True, default=str)
        result, warnings = policies.guard_task_output(
            payload,
            rule_why=str(detail.get("why") or ""),
            rule_suggest=str(detail.get("suggest") or ""),
            severity=str((state["facts"].get("task") or {}).get("severity") or ""),
            elapsed_minutes=int(detail.get("elapsed_minutes") or 0),
            threshold_minutes=int(detail.get("threshold_minutes") or 0),
            facts_text=facts_text,
        )
        return {"result": result, "warnings": warnings}

    graph = StateGraph(TaskExplainState)
    graph.add_node("load", load)
    graph.add_node("explain", explain)
    graph.add_node("parse", parse)

    graph.add_edge(START, "load")
    graph.add_edge("load", "explain")
    graph.add_edge("explain", "parse")
    graph.add_edge("parse", END)
    return graph.compile()
