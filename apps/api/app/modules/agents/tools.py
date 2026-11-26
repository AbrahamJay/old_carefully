"""事实层：把 service 能力包装成只读工具。

两个原则：
1. 图内节点只能通过这里取数，拿不到 ``Session``，从结构上杜绝「在 prompt 里随手查库」；
2. 工具同时以 Python 方法与 LangChain ``StructuredTool`` 暴露，阶段五直接调用，
   阶段七绑定给模型，属于同一份定义，不重复实现。

工具返回的是「给模型看的事实」，因此在这里完成脱敏（手机号、门牌），
原始档案不会离开本进程。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from ...core.enums import AssignmentStatus, OrderStatus, Role
from ...core.errors import ConflictError, ForbiddenError
from ...core.time import business_tz
from ...db.models import Order, User
from ..orders.service import OrderService
from .policies import scrub

# 服务中才能写记录；服务前提示允许「已派单/已接单」阶段查看
_PREP_ALLOWED_STATUSES = (OrderStatus.ASSIGNED, OrderStatus.IN_SERVICE)
_ACTIVE_ASSIGNMENTS = (AssignmentStatus.ASSIGNED, AssignmentStatus.ACCEPTED)

_GENDER_LABELS = {"male": "男", "female": "女"}


def _address_area(street: str, community: str) -> str:
    """地址只到街道+社区：楼栋门牌不外发给模型，具体门牌由员工看订单详情页。

    直接把 ``elder.address`` 丢给模型会同时踩两个坑：门牌泄露给第三方网关，
    以及 ``scrub`` 只抹掉「3 栋」却留下「202」这种半截门牌。
    """
    return " ".join(part for part in (street, community) if part)


class OrderIdArgs(BaseModel):
    order_id: int = Field(description="订单 ID")


@dataclass(frozen=True)
class OrderFacts:
    """一次工具调用的结果：已脱敏、只含生成文本所需字段。"""

    order_id: int
    order_no: str
    service_name: str
    duration_minutes: int
    scheduled_at: str
    order_status: str
    community: str
    elder_gender: str
    elder_age: int | None
    health_notes: str
    order_notes: str
    staff_name: str
    photo_count: int = 0
    # 地址只给到街道+社区（对话场景专用），门牌不外发给模型
    address_area: str = ""
    # 只告诉模型「这单有没有紧急联系人」，号码本身不外发
    emergency_available: bool = False

    def to_prompt_dict(self) -> dict[str, Any]:
        data = asdict(self)
        # 写记录与服务前提示不需要位置和联系方式，剔掉避免模型把它们写成注意事项
        data.pop("address_area", None)
        data.pop("emergency_available", None)
        return data

    @property
    def has_health_info(self) -> bool:
        return bool(self.health_notes.strip())


class AgentTools:
    """按「当前操作人」构造，权限校验复用订单服务，不另写一套判定。"""

    def __init__(self, orders: OrderService, actor: User) -> None:
        self._orders = orders
        self._actor = actor

    def order_facts(
        self, order_id: int, *, for_record: bool, photo_count: int = 0
    ) -> OrderFacts:
        """读取订单与老人事实。

        ``for_record=True`` 用于记录草稿（必须服务中）；``False`` 用于服务前提示
        （已派单或服务中）。状态不符抛 409，让前端提示刷新，而不是生成过时内容。
        """
        order = self._orders.get_for_actor(self._actor, order_id)
        self._ensure_status(order, for_record=for_record)
        self._ensure_assigned(order)
        return self._build_facts(order, photo_count=photo_count)

    def _ensure_status(self, order: Order, *, for_record: bool) -> None:
        if for_record:
            if order.status != OrderStatus.IN_SERVICE:
                raise ConflictError("订单当前不在服务中，无法生成记录草稿")
            return
        if order.status not in _PREP_ALLOWED_STATUSES:
            raise ConflictError("订单尚未派单，暂无服务前提示")

    def _ensure_assigned(self, order: Order) -> None:
        """员工只能操作派给自己的订单；管理员不在此限制（便于排查与代写）。"""
        if self._actor.role != Role.STAFF:
            return
        assigned = any(
            assignment.staff_id == self._actor.id and assignment.status in _ACTIVE_ASSIGNMENTS
            for assignment in order.assignments
        )
        if not assigned:
            raise ForbiddenError("该订单未派给你，无法生成内容")

    def _build_facts(self, order: Order, *, photo_count: int) -> OrderFacts:
        elder = order.elder
        scheduled = order.scheduled_at.astimezone(business_tz())
        age = None
        if elder.birth_year:
            age = scheduled.year - elder.birth_year
        return OrderFacts(
            order_id=order.id,
            order_no=order.order_no,
            service_name=order.service.name if order.service else "",
            duration_minutes=order.service.duration_minutes if order.service else 0,
            scheduled_at=scheduled.strftime("%Y-%m-%d %H:%M"),
            order_status=str(order.status),
            community=elder.community or "",
            elder_gender=_GENDER_LABELS.get(elder.gender, "未知"),
            elder_age=age,
            # 只保留有限长度：健康备注常是长段自由文本，过长既贵又容易淹没关键信息
            health_notes=scrub(elder.health_notes)[:300],
            order_notes=scrub(order.notes)[:300],
            staff_name=self._actor.name or "",
            photo_count=photo_count,
            address_area=_address_area(
                order.station.street if order.station else "", elder.community
            ),
            emergency_available=bool(elder.emergency_phone or elder.emergency_name),
        )

    def dispatch_facts(self, order_id: int) -> dict[str, Any]:
        """派单解释用事实：订单摘要 + 规则候选（含理由/风险/数据缺口）。

        候选由规则引擎计算，与 ``/admin/orders/{id}/candidates`` 完全同源；
        模型只负责把结果讲清楚，因此这里不做任何排序或筛选。
        """
        order = self._orders.get_for_actor(self._actor, order_id)
        report = self._orders.list_candidates(self._actor, order_id)
        scheduled = order.scheduled_at.astimezone(business_tz())
        elder = order.elder
        age = scheduled.year - elder.birth_year if elder.birth_year else None
        return {
            "order": {
                "order_no": order.order_no,
                "service": order.service.name if order.service else "",
                "station": order.station.name if order.station else "",
                "scheduled_at": scheduled.strftime("%Y-%m-%d %H:%M"),
                "duration_minutes": order.service.duration_minutes if order.service else 0,
                "status": str(order.status),
                "community": elder.community or "",
                "elder_age": age,
                # 只给有限长度的档案摘要，手机号/门牌在这里已抹掉
                "elder_note": scrub(elder.health_notes)[:120],
                "order_note": scrub(order.notes)[:120],
            },
            "candidates": [
                {
                    "staff_id": item.staff_id,
                    "name": item.name,
                    "score": item.score,
                    "load": item.load,
                    "capacity": item.capacity,
                    "skills": list(item.skills),
                    "reasons": list(item.reasons),
                    "risks": list(item.risks),
                }
                for item in report.candidates[:5]
            ],
            # 只带前 5 位被排除者，足够解释「为什么没他」，避免 prompt 膨胀
            "excluded": [
                {"name": item.name, "reasons": list(item.reasons)}
                for item in report.excluded[:5]
            ],
            "data_gaps": list(report.data_gaps),
        }

    # ------------------------------------------------------- 阶段七复用入口
    def chat_facts(self, order_id: int) -> dict[str, Any]:
        """「这单助手」的事实：与记录草稿同源，只覆盖当前这一单。

        状态限制比写记录宽（已派单也允许问），但权限校验完全复用订单服务：
        员工只能问派给自己的单，管理员不限。
        """
        facts = self.order_facts(order_id, for_record=False)
        data = facts.to_prompt_dict()
        # 照片数量对问答没有意义，去掉可少一个让模型乱猜的数字
        data.pop("photo_count", None)
        # 员工最常问的就是「去哪」：补上街道+社区。没有这个字段，模型只会答「没有地址」
        data["address_area"] = facts.address_area
        # 只给「有没有紧急联系人」：号码不外发，让模型引导员工去看订单详情
        data["emergency_available"] = facts.emergency_available
        return data

    def as_langchain_tools(self) -> list[StructuredTool]:
        """绑定给模型时使用；阶段五不调用，但定义与上方法完全一致。"""

        def _get_order_facts(order_id: int) -> str:
            import json

            facts = self.order_facts(order_id, for_record=False)
            return json.dumps(facts.to_prompt_dict(), ensure_ascii=False)

        return [
            StructuredTool.from_function(
                func=_get_order_facts,
                name="get_order_facts",
                description="读取订单的服务项目、时间、社区与老人健康提示（已脱敏）。",
                args_schema=OrderIdArgs,
            )
        ]

    @property
    def now(self) -> datetime:
        """注入时钟便于测试；工具内不直接调用 ``datetime.now``。"""
        return datetime.now(tz=business_tz())
