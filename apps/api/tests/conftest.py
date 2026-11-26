"""测试环境准备：在导入 app 之前设好环境变量，并给每个 pytest 进程派生独立测试库。

为什么每个进程一个库：用例开始前会对 schema 做 DROP/CREATE，两个 pytest 进程共用同一个库
会互相抢锁，PostgreSQL 直接报 ``DeadlockDetected`` —— PyCharm 里跑一份、命令行再跑一份就会撞上。
库名形如 ``socialoldcare_test_p12345``（xdist 下用 worker 名），跑完 auto DROP DATABASE ... WITH (FORCE)；
设 ``KEEP_TEST_DB=1`` 可保留现场排查。
"""

from __future__ import annotations

import atexit
import os
from pathlib import Path

from dotenv import dotenv_values
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEST_UPLOADS = Path(__file__).parent / "test-uploads"


def _base_test_url() -> str:
    """测试库的基准连接串：TEST_DATABASE_URL 优先，否则从 .env 的 DATABASE_URL 换库名派生。"""
    explicit = os.environ.get("TEST_DATABASE_URL", "").strip()
    if explicit:
        return explicit

    base = os.environ.get("DATABASE_URL", "").strip()
    if not base:
        base = dotenv_values(PROJECT_ROOT / ".env").get("DATABASE_URL") or ""
    if not base:
        raise SystemExit("未找到 DATABASE_URL：请在 .env 或环境变量中配置 PostgreSQL 连接串")
    url = make_url(base)
    if url.get_backend_name() != "postgresql":
        raise SystemExit(f"测试库必须是 PostgreSQL，当前为 {url.get_backend_name()}")
    return url.set(database="socialoldcare_test").render_as_string(hide_password=False)


def _isolated_url(base_url: str) -> str:
    """在基准库名后再挂一个进程后缀，保证并发跑 pytest 时各用各的库。"""
    url = make_url(base_url)
    suffix = os.environ.get("PYTEST_XDIST_WORKER") or f"p{os.getpid()}"
    return url.set(database=f"{url.database}_{suffix}").render_as_string(hide_password=False)


def _admin_engine(url_str: str):
    """连到 postgres 维护库：CREATE/DROP DATABASE 不能在使用中的库里执行。"""
    admin_url = make_url(url_str).set(database="postgres")
    return create_engine(admin_url, isolation_level="AUTOCOMMIT")


def _ensure_database(url_str: str) -> None:
    db_name = make_url(url_str).database or ""
    engine = _admin_engine(url_str)
    try:
        with engine.connect() as conn:
            exists = conn.execute(
                text("select 1 from pg_database where datname = :name"), {"name": db_name}
            ).scalar()
            if not exists:
                conn.execute(text(f'create database "{db_name}"'))
    except Exception as exc:
        raise SystemExit(
            f"无法准备测试库 {db_name}：{exc}。请确认数据库账号具备 CREATEDB 权限，"
            "或手动建好该库、用 TEST_DATABASE_URL 指定一个已有库。"
        ) from exc
    finally:
        engine.dispose()


def _reset_schema(url_str: str) -> None:
    engine = create_engine(url_str)
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    engine.dispose()


def _drop_database(url_str: str) -> None:
    """进程退出时删掉本进程的库；FORCE 会踢掉仍挂在上面的连接。"""
    db_name = make_url(url_str).database or ""
    try:
        # 先释放应用连接池，减少被 FORCE 直接掐断的报错噪音
        from app.db import engine as app_engine

        app_engine.dispose()
    except Exception as exc:  # noqa: BLE001 - 解释器退出阶段尽力而为
        print(f"[warn] 释放应用连接池失败（不影响清理）：{exc}")
    try:
        engine = _admin_engine(url_str)
        with engine.connect() as conn:
            conn.execute(text(f'drop database if exists "{db_name}" with (force)'))
        engine.dispose()
    except Exception as exc:  # noqa: BLE001
        print(f"[warn] 清理测试库 {db_name} 失败：{exc}")


TEST_DATABASE_URL = _isolated_url(_base_test_url())
_db_name = make_url(TEST_DATABASE_URL).database or ""

# 保险丝：下面会 DROP SCHEMA / DROP DATABASE，库名必须是测试库，防止误配到主库/生产
if not {"test", "ci"} & set(_db_name.split("_")):
    raise SystemExit(
        f"拒绝对非 *_test / *_ci 命名的库执行 DROP SCHEMA（当前库名：{_db_name or '未知'}）。"
        "请检查 TEST_DATABASE_URL 是否指向测试库。"
    )

_ensure_database(TEST_DATABASE_URL)
_reset_schema(TEST_DATABASE_URL)

if TEST_UPLOADS.exists():
    for item in TEST_UPLOADS.iterdir():
        item.unlink()
    TEST_UPLOADS.rmdir()

# 必须在 import app.* 之前设置：settings 是模块级单例，导入后再改环境变量不会生效
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ["AUTO_SEED"] = "true"
os.environ["JWT_SECRET"] = "test-secret-please-use-32-bytes-minimum"
os.environ["UPLOAD_DIR"] = str(TEST_UPLOADS)
# 测试固定用本地磁盘 + 后端转发，绝不连真实对象存储（.env 里可能配了 MinIO）
os.environ["STORAGE_PROVIDER"] = "local"
os.environ["FILE_DELIVERY"] = "proxy"
# Agent 固定用 mock 模型：测试不产生真实调用与费用，也不依赖网络
os.environ["AGENT_ENABLED"] = "true"
os.environ["LLM_PROVIDER"] = "mock"
os.environ["LLM_MODEL"] = "mock"
os.environ["AGENT_DAILY_LIMIT_PER_USER"] = "50"

if not os.environ.get("KEEP_TEST_DB"):
    atexit.register(_drop_database, TEST_DATABASE_URL)
