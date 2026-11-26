"""单轮图与流式生成：员工「这单助手」。

与其它场景的差别只有一处：回答要边说边出字。因此这里除了
``build_chat_graph``（JSON 接口、图编排）之外，还提供 ``ChatStreamSession``（SSE）。
两者共用同一份 prompt 与同一套脱敏规则，避免「流式与非流式回答不一致」。

事实由服务层预先取好（同阶段六的做法）：图与流式都只消费 ``facts``，
这样权限校验、降级判定只发生一次。
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any, TypedDict

from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.graph import END, START, StateGraph

from .. import policies, prompts


def _facts_text(facts: dict[str, Any]) -> str:
    """事实全文：护栏拿它做数字比对，与缓存指纹用的是同一份序列化口径。"""
    return json.dumps(facts, ensure_ascii=False, sort_keys=True, default=str)


# 对话输出是自然语言正文，不是 JSON：必须显式关掉适配器默认的 json_mode。
# 不关的话请求会带 response_format=json_object，与「不要 JSON」的 prompt 打架，
# 网关只会回空串或一串空格（前端表现为「(没有回答)」）。
_CHAT_MODEL_KWARGS: dict[str, Any] = {"json_mode": False}


class ChatState(TypedDict, total=False):
    facts: dict
    raw: str
    answer: str
    warnings: list[str]


def build_chat_graph(
    *,
    model: BaseChatModel,
    callback,
    facts: dict,
    question: str,
    history: list[dict[str, str]],
    max_tokens: int,
):
    """构造并编译图；``history`` 由服务层裁剪、脱敏后再传进来。"""

    def load(state: ChatState) -> ChatState:
        return {"facts": facts}

    def generate(state: ChatState) -> ChatState:
        messages = prompts.chat_messages(
            state["facts"], history=history, question=question
        )
        response = model.invoke(
            messages,
            max_tokens=max_tokens,
            config={"callbacks": [callback]},
            **_CHAT_MODEL_KWARGS,
        )
        return {"raw": response.content}

    def guard(state: ChatState) -> ChatState:
        answer, warnings = policies.guard_chat_text(
            state.get("raw", ""), facts_text=_facts_text(state["facts"])
        )
        return {"answer": answer, "warnings": warnings}

    graph = StateGraph(ChatState)
    graph.add_node("load", load)
    graph.add_node("generate", generate)
    graph.add_node("guard", guard)

    graph.add_edge(START, "load")
    graph.add_edge("load", "generate")
    graph.add_edge("generate", "guard")
    graph.add_edge("guard", END)
    return graph.compile()


class ChatStreamSession:
    """一次流式回答：迭代产出文本增量，迭代结束后从属性取完整结果。

    不用 LangGraph 跑流式：图的 ``invoke`` 拿不到增量 token，接自定义流要多一层协议，
    而这里只有一个节点。prompt 与护栏仍与图共用，所以两条路径的输出口径一致。
    """

    def __init__(
        self,
        *,
        model: BaseChatModel,
        callback,
        facts: dict,
        question: str,
        history: list[dict[str, str]],
        max_tokens: int,
    ) -> None:
        self._model = model
        self._callback = callback
        self._facts = facts
        self._question = question
        self._history = history
        self._max_tokens = max_tokens
        self._guard = policies.ChatStreamGuard(facts_text=_facts_text(facts))
        # 迭代结束后由服务层读取：用于 SSE 的 done 事件与审计汇总行
        self.answer = ""
        self.warnings: list[str] = []

    def __iter__(self) -> Iterator[str]:
        messages = prompts.chat_messages(
            self._facts, history=self._history, question=self._question
        )
        parts: list[str] = []
        try:
            for chunk in self._model.stream(
                messages,
                max_tokens=self._max_tokens,
                config={"callbacks": [self._callback]},
                **_CHAT_MODEL_KWARGS,
            ):
                text = chunk.content if isinstance(chunk.content, str) else ""
                piece = self._guard.feed(text)
                if piece:
                    parts.append(piece)
                    yield piece
            tail = self._guard.flush()
            if tail:
                parts.append(tail)
                yield tail
        finally:
            # 客户端中途断开也会走到这里：已发出的字要留住，审计里的字数才真实
            self.answer = "".join(parts)
            self.warnings = self._guard.finalize(self.answer)
