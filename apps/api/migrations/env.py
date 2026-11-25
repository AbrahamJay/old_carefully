"""Alembic 运行环境。

连接串取自应用配置（单一来源），不使用 alembic.ini 里的 sqlalchemy.url。
"""

from __future__ import annotations

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import create_engine, pool

# 让 alembic 无论从哪个工作目录被调用都能导入 app 包
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings  # noqa: E402
from app.db import models  # noqa: E402,F401  导入即注册全部表到 Base.metadata
from app.db.base import Base  # noqa: E402

config = context.config

if config.config_file_name is not None:
    # disable_existing_loggers 默认 True 会把应用与 uvicorn 已注册的 logger 全部禁用，
    # 一旦启动时真的跑了一次迁移，进程后续的 INFO 日志会全部消失（恰好在部署时最需要日志）。
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(settings.database_url, poolclass=pool.NullPool)
    try:
        with connectable.connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                compare_type=True,
            )
            with context.begin_transaction():
                context.run_migrations()
    finally:
        connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
