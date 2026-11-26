"""Agent 路由。

所有端点都只读：生成结果回填输入框或展示给管理员，真正写库仍走原有业务接口。
``/agent/status`` 对已登录用户开放，前端据此隐藏入口，而不是等用户点了才报错。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from ...api.deps import get_agent_service, get_current_user, require_roles
from ...core.enums import Role
from ...db.models import User
from .schemas import (
    AgentStatusOut,
    ChatIn,
    ChatOut,
    DispatchSuggestIn,
    DispatchSuggestOut,
    PrepBriefIn,
    PrepBriefOut,
    RecordDraftIn,
    RecordDraftOut,
    TaskExplainIn,
    TaskExplainOut,
)
from .service import AgentService

router = APIRouter(tags=["Agent"])


@router.get("/agent/status", response_model=AgentStatusOut)
def agent_status(
    user: User = Depends(get_current_user),
    service: AgentService = Depends(get_agent_service),
) -> AgentStatusOut:
    """当前用户能否使用 AI、今天还剩多少次。"""
    return service.status(user)


@router.post("/agent/staff/prep-brief", response_model=PrepBriefOut)
def prep_brief(
    payload: PrepBriefIn,
    user: User = Depends(require_roles(Role.STAFF)),
    service: AgentService = Depends(get_agent_service),
) -> PrepBriefOut:
    """服务前提示：进入已派单订单时调用，档案为空则不产生模型调用。"""
    return service.prep_brief(user, payload.order_id)


@router.post("/agent/staff/record-draft", response_model=RecordDraftOut)
def record_draft(
    payload: RecordDraftIn,
    user: User = Depends(require_roles(Role.STAFF)),
    service: AgentService = Depends(get_agent_service),
) -> RecordDraftOut:
    """记录代写：只返回文本，不写 service_records。"""
    return service.record_draft(
        user, payload.order_id, payload.rough_notes, payload.photo_count
    )


@router.post("/agent/staff/chat", response_model=ChatOut)
def chat(
    payload: ChatIn,
    user: User = Depends(require_roles(Role.STAFF)),
    service: AgentService = Depends(get_agent_service),
) -> ChatOut:
    """「这单助手」：绑定单张订单的窄问答，只回答不写库。"""
    return service.chat(
        user, payload.order_id, payload.question, [item.model_dump() for item in payload.history]
    )


@router.post("/agent/staff/chat/stream")
def chat_stream(
    payload: ChatIn,
    user: User = Depends(require_roles(Role.STAFF)),
    service: AgentService = Depends(get_agent_service),
) -> StreamingResponse:
    """「这单助手」流式版：SSE 逐字返回。

    额度、权限、订单状态在开始推流前校验完：这样 403/409/429/503 仍是正常的
    JSON 错误响应，前端不用区分「开流前失败」与「开流后失败」两套逻辑。
    """
    plan = service.prepare_chat(
        user, payload.order_id, payload.question, [item.model_dump() for item in payload.history]
    )
    return StreamingResponse(
        service.chat_stream(plan),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            # 不加这一项，nginx 会攒够一个缓冲区才下发，逐字效果就没了
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.post("/agent/admin/dispatch-suggest", response_model=DispatchSuggestOut)
def dispatch_suggest(
    payload: DispatchSuggestIn,
    user: User = Depends(require_roles(Role.ADMIN)),
    service: AgentService = Depends(get_agent_service),
) -> DispatchSuggestOut:
    """派单建议解释：候选由规则给出，模型只解释为什么推荐它。"""
    return service.dispatch_suggest(user, payload.order_id, force_refresh=payload.force_refresh)


@router.post("/agent/admin/task-explain", response_model=TaskExplainOut)
def task_explain(
    payload: TaskExplainIn,
    user: User = Depends(require_roles(Role.ADMIN)),
    service: AgentService = Depends(get_agent_service),
) -> TaskExplainOut:
    """异常解释：把扫描规则的事实变成人话与可执行动作，不自动处理。"""
    return service.task_explain(user, payload.task_id, force_refresh=payload.force_refresh)
