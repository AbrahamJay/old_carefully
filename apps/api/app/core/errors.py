"""领域异常与统一错误响应。

设计要点：
1. 业务代码只抛 AppError 子类，不依赖 FastAPI。
2. 响应体同时保留 ``detail`` 字段，兼容既有前端对 ``{"detail": ...}`` 的解析。
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

logger = logging.getLogger(__name__)


class AppError(Exception):
    code: str = "internal_error"
    http_status: int = 500
    default_message: str = "服务器内部错误"

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        http_status: int | None = None,
    ) -> None:
        self.message = message or self.default_message
        if code is not None:
            self.code = code
        if http_status is not None:
            self.http_status = http_status
        super().__init__(self.message)


class BadRequestError(AppError):
    code = "invalid_argument"
    http_status = 400
    default_message = "请求参数有误"


class UnauthorizedError(AppError):
    code = "unauthorized"
    http_status = 401
    default_message = "未登录或登录已过期"


class ForbiddenError(AppError):
    code = "forbidden"
    http_status = 403
    default_message = "没有权限"


class NotFoundError(AppError):
    code = "not_found"
    http_status = 404
    default_message = "资源不存在"


class ConflictError(AppError):
    code = "conflict"
    http_status = 409
    default_message = "操作冲突"


class FeatureUnavailableError(AppError):
    code = "unavailable"
    http_status = 501
    default_message = "该功能尚未启用"


class ExternalServiceError(AppError):
    """下游依赖（对象存储、支付网关等）不可用。"""

    code = "upstream_error"
    http_status = 502
    default_message = "外部服务暂时不可用"


def _payload(exc: AppError, request: Request) -> dict:
    return {
        "detail": exc.message,
        "code": exc.code,
        "request_id": getattr(request.state, "request_id", ""),
    }


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(status_code=exc.http_status, content=_payload(exc, request))

    @app.exception_handler(IntegrityError)
    async def _handle_integrity_error(request: Request, exc: IntegrityError) -> JSONResponse:
        logger.warning("数据库约束冲突: %s", exc.orig)
        return JSONResponse(
            status_code=409,
            content={
                "detail": "数据冲突，请重试",
                "code": "conflict",
                "request_id": getattr(request.state, "request_id", ""),
            },
        )
