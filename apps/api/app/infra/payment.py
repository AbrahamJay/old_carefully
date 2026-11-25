"""在线支付渠道实现。"""

from __future__ import annotations

import uuid

from ..core.errors import FeatureUnavailableError
from .ports import ChargeResult


class MockOnlineGateway:
    """演示用模拟支付：不产生真实资金流，仅生成模拟流水。"""

    name = "mock"

    def charge(self, amount_cents: int, *, kind: str, operator_id: int | None) -> ChargeResult:
        return ChargeResult(
            provider=self.name,
            transaction_id=f"MOCK-{uuid.uuid4().hex[:12].upper()}",
            raw={"method": "mock", "kind": kind, "customer_id": operator_id},
        )


class WechatPayGateway:
    """微信支付占位实现。"""

    name = "wechat"

    def charge(self, amount_cents: int, *, kind: str, operator_id: int | None) -> ChargeResult:
        raise FeatureUnavailableError("微信支付尚未接入")
