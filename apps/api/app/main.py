"""应用装配。

只做三件事：注册中间件与错误处理、初始化数据库、挂载路由。
业务能力全部位于 ``app/modules``，本文件不出现任何业务逻辑。
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.router import api_router
from .core.config import settings
from .core.errors import install_error_handlers
from .core.logging import RequestIdMiddleware, setup_logging
from .db import SessionLocal, init_db
from .db.seed import seed


@asynccontextmanager
async def lifespan(_: FastAPI):
    setup_logging()
    init_db()
    if settings.auto_seed:
        with SessionLocal() as db:
            seed(db)
    yield


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="社区养老服务管家：老人档案、下单、派单、履约记录、资金结算。",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RequestIdMiddleware)

install_error_handlers(app)

app.include_router(api_router)


@app.get("/")
def root() -> dict:
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "docs": "/docs",
        "health": "/healthz",
        "api": "/api/v1",
    }


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True, "env": settings.app_env}
