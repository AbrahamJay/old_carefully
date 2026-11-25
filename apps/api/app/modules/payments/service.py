"""订单资金结算。

这里是"定金/尾款/退款"规则的唯一实现：
在线支付、线下收款、取消退款都走同一套计算，避免各入口口径不一致。
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import inspect as sa_inspect
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...core.enums import OrderStatus, PaymentProvider, PaymentRecordStatus, PaymentStatus
from ...core.errors import BadRequestError, ConflictError
from ...db.models import Order, Payment, ServiceRecord, User
from ...infra.ports import OnlinePaymentGateway

SettlementKind = Literal["定金", "尾款"]


@dataclass(frozen=True)
class PaymentTotals:
    paid_cents: int
    refunded_cents: int
    net_cents: int
    remaining_cents: int


@dataclass(frozen=True)
class Settlement:
    amount_cents: int
    kind: SettlementKind
    net_after_cents: int


class PaymentService:
    def __init__(self, db: Session, gateway: OnlinePaymentGateway) -> None:
        self._db = db
        self._gateway = gateway

    # ------------------------------------------------------------------ 查询
    def payments_of(self, order: Order) -> Sequence[Payment]:
        """优先复用已 eager load 的关联集合，避免列表页产生 N+1。"""
        if "payments" not in sa_inspect(order).unloaded:
            return order.payments
        return self._db.scalars(select(Payment).where(Payment.order_id == order.id)).all()

    def totals(self, order: Order) -> PaymentTotals:
        payments = self.payments_of(order)
        paid = sum(p.amount_cents for p in payments if p.status == PaymentRecordStatus.PAID)
        refunded = sum(p.amount_cents for p in payments if p.status == PaymentRecordStatus.REFUNDED)
        net = max(paid - refunded, 0)
        return PaymentTotals(
            paid_cents=paid,
            refunded_cents=refunded,
            net_cents=net,
            remaining_cents=max(order.amount_cents - net, 0),
        )

    def find_outstanding_order(self, customer_id: int) -> Order | None:
        """存在未结清尾款的已完成订单时返回它。"""
        orders = self._db.scalars(
            select(Order).where(
                Order.customer_id == customer_id,
                Order.status == OrderStatus.COMPLETED,
                Order.payment_status != PaymentStatus.REFUNDED,
            )
        ).all()
        for order in orders:
            if self.totals(order).remaining_cents > 0:
                return order
        return None

    # ------------------------------------------------------------------ 计算
    def plan(self, order: Order, *, require_completed_for_final: bool) -> Settlement:
        totals = self.totals(order)
        if totals.remaining_cents <= 0:
            raise BadRequestError("订单已结清", code="already_settled")

        if order.deposit_cents > 0 and totals.net_cents < order.deposit_cents:
            amount = order.deposit_cents - totals.net_cents
            kind: SettlementKind = "定金"
        else:
            if require_completed_for_final and order.status != OrderStatus.COMPLETED:
                raise ConflictError("服务完成后再支付尾款")
            amount = totals.remaining_cents
            kind = "尾款"
        return Settlement(amount, kind, totals.net_cents + amount)

    # ------------------------------------------------------------------ 收款
    def pay_online(self, order: Order, actor: User) -> tuple[Payment, Settlement]:
        if order.status == OrderStatus.CANCELLED:
            raise ConflictError("已取消的订单不能支付")
        plan = self.plan(order, require_completed_for_final=True)
        result = self._gateway.charge(plan.amount_cents, kind=plan.kind, operator_id=actor.id)
        payment = Payment(
            order_id=order.id,
            provider=result.provider,
            amount_cents=plan.amount_cents,
            status=PaymentRecordStatus.PAID,
            transaction_id=result.transaction_id,
            raw=result.raw,
        )
        self._db.add(payment)
        self._apply_payment_status(order, plan.net_after_cents, provider=result.provider)
        self._confirm_record_if_settled(order, plan.net_after_cents)
        return payment, plan

    def pay_offline(self, order: Order, actor: User, *, method: str) -> tuple[Payment, Settlement]:
        plan = self.plan(order, require_completed_for_final=False)
        payment = Payment(
            order_id=order.id,
            provider=PaymentProvider.OFFLINE,
            amount_cents=plan.amount_cents,
            status=PaymentRecordStatus.PAID,
            transaction_id=f"OFFLINE-{order.order_no}-{uuid.uuid4().hex[:6].upper()}",
            raw={"method": method, "kind": plan.kind, "operator_id": actor.id},
        )
        self._db.add(payment)
        self._apply_payment_status(order, plan.net_after_cents, provider=PaymentProvider.OFFLINE)
        self._confirm_record_if_settled(order, plan.net_after_cents)
        return payment, plan

    def refund(self, order: Order, actor: User, *, reason: str) -> Payment:
        totals = self.totals(order)
        if totals.net_cents <= 0:
            raise BadRequestError("没有可退款项")

        source = next(
            (p for p in self.payments_of(order) if p.status == PaymentRecordStatus.PAID), None
        )
        provider = source.provider if source else PaymentProvider.MOCK
        payment = Payment(
            order_id=order.id,
            provider=provider,
            amount_cents=totals.net_cents,
            status=PaymentRecordStatus.REFUNDED,
            transaction_id=f"REFUND-{order.order_no}-{uuid.uuid4().hex[:6].upper()}",
            raw={"reason": reason, "operator_id": actor.id},
        )
        self._db.add(payment)
        order.payment_status = PaymentStatus.REFUNDED
        return payment

    # ------------------------------------------------------------------ 内部
    def _apply_payment_status(self, order: Order, net_after: int, *, provider: str) -> None:
        if net_after < order.amount_cents:
            order.payment_status = PaymentStatus.DEPOSIT_PAID
            return
        if provider == PaymentProvider.OFFLINE:
            order.payment_status = PaymentStatus.PAID_OFFLINE
        elif provider == PaymentProvider.MOCK:
            order.payment_status = PaymentStatus.PAID_MOCK
        else:
            order.payment_status = f"paid_{provider}"

    def _confirm_record_if_settled(self, order: Order, net_after: int) -> None:
        """全额收款后自动视为长辈已确认服务（在线/线下口径一致）。"""
        if order.status != OrderStatus.COMPLETED or net_after < order.amount_cents:
            return
        record = self._db.scalars(
            select(ServiceRecord)
            .where(ServiceRecord.order_id == order.id)
            .order_by(ServiceRecord.id.desc())
        ).first()
        if record is not None:
            record.elder_confirmed = True
