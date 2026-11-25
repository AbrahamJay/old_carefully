"""业务标识生成。"""

from __future__ import annotations

import secrets
from datetime import datetime


def new_order_no(prefix: str = "ORD") -> str:
    return prefix + datetime.now().strftime("%Y%m%d%H%M%S") + f"{secrets.randbelow(10000):04d}"


def new_invite_code() -> str:
    return secrets.token_hex(3).upper()
