"""数据库初始化。

建表与增量变更统一交给 Alembic，不再维护手写 ALTER 语句。
"""

from __future__ import annotations

import logging

from ..core.config import settings
from .migrate import run_migrations

logger = logging.getLogger(__name__)


def init_db() -> None:
    """把数据库升级到最新 revision。

    ``AUTO_MIGRATE=false`` 时跳过，交给运维手动执行 ``alembic upgrade head``；
    单机部署保持默认 True，避免"忘了跑迁移导致启动报错"。
    """
    if not settings.auto_migrate:
        logger.info("AUTO_MIGRATE=false，跳过自动迁移")
        return
    run_migrations()
