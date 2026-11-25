"""Alembic 迁移的编程入口。

应用启动时自动升级到 head（``AUTO_MIGRATE=false`` 可关闭），
运维也可以直接执行 ``.venv/bin/alembic upgrade head``。

启动日志只在新迁移真正执行时提示：版本已是最新则静默跳过（debug 级别），
避免每次启动都打印「执行数据库迁移」，让人误以为在重复建表。
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]


# 版本核对时会触发的 alembic 内部 logger（Context impl / setup plugin 等）
_ALEMBIC_LOGGERS = (
    "alembic",
    "alembic.runtime.migration",
    "alembic.runtime.plugins",
    "alembic.script",
)


@contextmanager
def _quiet_alembic() -> Iterator[None]:
    """版本核对期间把 alembic 内部探针日志压到 WARNING。

    这些日志只有排查迁移问题时才有用，平时只会让启动输出变噪。
    只包住核对过程；真正执行 upgrade 时恢复级别，Running upgrade 仍可见。
    """
    saved = {name: logging.getLogger(name).level for name in _ALEMBIC_LOGGERS}
    try:
        for name in _ALEMBIC_LOGGERS:
            logging.getLogger(name).setLevel(logging.WARNING)
        yield
    finally:
        for name, level in saved.items():
            logging.getLogger(name).setLevel(level)


def alembic_config() -> Config:
    """构造 Alembic 配置：脚本目录锚定项目根，连接串由 env.py 从 settings 读取。"""
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(PROJECT_ROOT / "migrations"))
    return config


def current_revision() -> str | None:
    """读取库中已应用的 revision；全新库（无 alembic_version 表）返回 None。"""
    # 函数内导入：避免 app.db 包初始化时 init -> migrate -> session 的顺序问题
    from .session import engine

    with engine.connect() as conn:
        return MigrationContext.configure(conn).get_current_revision()


def head_revision(config: Config) -> str | None:
    """代码侧最新 revision（迁移脚本目录的 head）。"""
    return ScriptDirectory.from_config(config).get_current_head()


def run_migrations(revision: str = "head") -> None:
    config = alembic_config()
    if revision == "head":
        with _quiet_alembic():
            current, target = current_revision(), head_revision(config)
        # 迁移目录为空（漏拷/误删）时不能当成“已最新”而静默跳过，否则一张表都不会建
        if target is None:
            raise RuntimeError("migrations/versions 下没有可用 revision，无法建表")
        if current == target:
            # 每次启动只做一次版本核对，没有实际迁移时不输出 INFO
            logger.debug("数据库已是最新 revision %s，跳过迁移", current)
            return
        logger.info("执行数据库迁移 %s -> %s", current or "空库", target)
    else:
        logger.info("执行数据库迁移 -> %s", revision)

    command.upgrade(config, revision)
