"""价格与定金规则（单一实现，供下单、种子数据和结算复用）。"""

from __future__ import annotations

from ..core.config import settings


def calc_deposit(amount_cents: int) -> int:
    """按配置比例计算定金，四舍五入到分。"""
    if amount_cents <= 0:
        return 0
    return int(amount_cents * settings.deposit_ratio + 0.5)
