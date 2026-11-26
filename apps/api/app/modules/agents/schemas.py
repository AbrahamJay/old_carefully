"""Agent 接口的出入参。"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class PrepBriefIn(BaseModel):
    order_id: int = Field(gt=0, description="订单 ID")


class PrepBriefOut(BaseModel):
    order_id: int
    items: list[str] = Field(default_factory=list, description="服务前提示，2-5 条")
    warnings: list[str] = Field(default_factory=list)
    model: str = ""
    latency_ms: int = 0


class RecordDraftIn(BaseModel):
    order_id: int = Field(gt=0)
    rough_notes: str = Field(
        min_length=1, max_length=500, description="员工口述要点，1-500 字"
    )
    photo_count: int = Field(default=0, ge=0, le=9, description="已上传照片数量")

    @field_validator("rough_notes")
    @classmethod
    def _strip_notes(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("请先写下本次服务的关键内容")
        return stripped


class RecordDraftOut(BaseModel):
    content: str = Field(default="", description="按五段结构整理的记录正文")
    prep_brief: list[str] = Field(default_factory=list, description="给家属的提示")
    warnings: list[str] = Field(
        default_factory=list, description="需要员工注意的提示码（如 redline、missing_section）"
    )
    model: str = ""
    latency_ms: int = 0


class AgentStatusOut(BaseModel):
    """前端据此决定是否渲染 AI 入口，并展示剩余次数。"""

    enabled: bool
    provider: str
    model: str
    daily_limit: int
    used_today: int
    remaining: int
    prep_brief_enabled: bool
    # 管理端两个解释场景的可用性单独下发：角色不匹配时前端直接隐藏按钮
    admin_scenarios: list[str] = Field(default_factory=list)
    admin_daily_limit: int = 0
    admin_remaining: int = 0
    # 对话是单独一套额度：否则一次多轮问答就把写记录的额度吃完了
    chat_enabled: bool = False
    chat_daily_limit: int = 0
    chat_used_today: int = 0
    chat_remaining: int = 0


class ChatTurnIn(BaseModel):
    """历史消息：由前端随请求带上来，服务端不落库。"""

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=400)


class ChatIn(BaseModel):
    order_id: int = Field(gt=0, description="订单 ID（对话固定绑定这一单）")
    question: str = Field(min_length=1, max_length=200, description="本次提问，1-200 字")
    history: list[ChatTurnIn] = Field(
        default_factory=list,
        max_length=12,
        description="最近几轮对话，超出部分由服务端再裁剪",
    )

    @field_validator("question")
    @classmethod
    def _strip_question(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("请先写下问题")
        return stripped


class ChatOut(BaseModel):
    """「这单助手」回答。没有 cache 态：对话上下文每次都不同。"""

    order_id: int
    answer: str = ""
    intent: str = ""
    warnings: list[str] = Field(default_factory=list)
    # rule=急症/越界等固定回答，未调用模型
    source: Literal["llm", "rule"] = "llm"
    trace_id: str = ""
    model: str = ""
    latency_ms: int = 0
    remaining: int = 0


class DispatchSuggestIn(BaseModel):
    order_id: int = Field(gt=0, description="订单 ID")
    force_refresh: bool = Field(default=False, description="跳过缓存，重新生成")


class DispatchRecommendationOut(BaseModel):
    """首选人始终来自规则引擎，模型只能解释，不能改。"""

    staff_id: int
    name: str = ""
    score: int = 0


class DispatchAlternativeOut(BaseModel):
    staff_id: int
    name: str = ""
    note: str = ""


class DispatchExcludedOut(BaseModel):
    """被硬条件挡住的员工：前端折叠展示，避免管理员反复找「为什么没他」。"""

    name: str = ""
    reasons: list[str] = Field(default_factory=list)


class DispatchSuggestOut(BaseModel):
    order_id: int
    recommendation: DispatchRecommendationOut | None = None
    summary: str = ""
    why: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    data_gaps: list[str] = Field(default_factory=list)
    alternatives: list[DispatchAlternativeOut] = Field(default_factory=list)
    excluded: list[DispatchExcludedOut] = Field(default_factory=list)
    # llm=模型生成；cache=复用缓存；rule=模型不可用或输出不合格时的规则文案
    source: Literal["llm", "cache", "rule"] = "rule"
    warnings: list[str] = Field(default_factory=list)
    trace_id: str = ""
    model: str = ""
    latency_ms: int = 0
    facts_hash: str = ""
    generated_at: datetime


class TaskExplainIn(BaseModel):
    task_id: int = Field(gt=0, description="异常任务 ID")
    force_refresh: bool = Field(default=False, description="跳过缓存，重新生成")


class ExplainActionOut(BaseModel):
    """动作只能取自白名单，前端按枚举映射跳转，模型不能发明动作。"""

    action: str
    label: str = ""


class TaskExplainOut(BaseModel):
    task_id: int
    type: str = ""
    title: str = ""
    what_happened: str = ""
    why: str = ""
    next_actions: list[ExplainActionOut] = Field(default_factory=list)
    escalate: bool = False
    data_gaps: list[str] = Field(default_factory=list)
    source: Literal["llm", "cache", "rule"] = "rule"
    warnings: list[str] = Field(default_factory=list)
    trace_id: str = ""
    model: str = ""
    latency_ms: int = 0
    facts_hash: str = ""
    generated_at: datetime
