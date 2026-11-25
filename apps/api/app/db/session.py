from __future__ import annotations

from collections.abc import Generator, Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from ..core.config import settings


def _engine_options() -> dict[str, object]:
    return {
        # 云上 PG 的空闲连接会被 NAT/安全组静默掐断：pre_ping + recycle 双重兜底
        "pool_pre_ping": True,
        "pool_size": 10,
        "max_overflow": 20,
        "pool_recycle": 1800,
        "pool_timeout": 30,
    }


engine = create_engine(settings.database_url, **_engine_options())

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)


@contextmanager
def session_scope() -> Iterator[Session]:
    """非 HTTP 场景（脚本、后台任务）使用的会话上下文。"""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_db() -> Generator[Session, None, None]:
    """FastAPI 依赖：请求级会话，异常时回滚由 session.close 兜底。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
