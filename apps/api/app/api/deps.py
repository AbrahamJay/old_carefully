"""依赖装配。

所有 service 的构造集中在这里，路由只声明"我需要哪个服务"。
新增模块时只需在此追加一个 provider，路由与业务代码都不用关心组装细节；
后续 Agent 接入也可以直接复用同一批 provider。
"""

from __future__ import annotations

from collections.abc import Callable
from functools import lru_cache

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from ..core.config import settings
from ..core.enums import Role, UserStatus
from ..core.errors import ForbiddenError, UnauthorizedError
from ..core.security import decode_access_token
from ..db.models import User
from ..db.session import get_db
from ..infra.payment import MockOnlineGateway, WechatPayGateway
from ..infra.ports import FileStorage, OnlinePaymentGateway
from ..infra.storage import build_local_storage, build_storage
from ..modules.admin import AdminService
from ..modules.audit import AuditService
from ..modules.auth import AuthService
from ..modules.catalog import CatalogService
from ..modules.elders import ElderService
from ..modules.elders.repository import ElderRepository
from ..modules.files import FileService
from ..modules.notifications import NotificationService
from ..modules.orders import OrderService
from ..modules.orders.repository import OrderRepository
from ..modules.org import StaffService, StationService, SupplierService
from ..modules.payments import PaymentService

bearer_scheme = HTTPBearer(auto_error=False)


# --------------------------------------------------------------------- 身份
def _resolve_user(credentials: HTTPAuthorizationCredentials, db: Session) -> User:
    try:
        payload = decode_access_token(credentials.credentials)
        user_id = int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError) as exc:
        raise UnauthorizedError() from exc
    user = db.get(User, user_id)
    if user is None or user.status != UserStatus.ACTIVE:
        raise UnauthorizedError("账号不可用")
    return user


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise UnauthorizedError()
    return _resolve_user(credentials, db)


def get_file_viewer(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User | None:
    """文件下载的可选身份：``REQUIRE_FILE_AUTH`` 关闭时返回 None，兼容前端直连。"""
    if not settings.require_file_auth:
        return None
    if credentials is None:
        raise UnauthorizedError()
    return _resolve_user(credentials, db)


def require_roles(*roles: Role | str) -> Callable[..., User]:
    allowed = tuple(str(role) for role in roles)

    def checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed:
            raise ForbiddenError()
        return user

    return checker


# ------------------------------------------------------------ 基础设施适配器
@lru_cache
def get_online_gateway() -> OnlinePaymentGateway:
    if settings.online_payment_provider == "wechat":
        return WechatPayGateway()
    return MockOnlineGateway()


@lru_cache
def get_storage() -> FileStorage:
    return build_storage()


@lru_cache
def get_local_storage() -> FileStorage:
    """本地兜底存储：切换 provider 后用于继续读历史文件。"""
    return build_local_storage()


# ---------------------------------------------------------------- 领域服务
def get_auth_service(db: Session = Depends(get_db)) -> AuthService:
    return AuthService(db)


def get_notification_service(db: Session = Depends(get_db)) -> NotificationService:
    return NotificationService(db)


def get_audit_service(db: Session = Depends(get_db)) -> AuditService:
    return AuditService(db)


def get_catalog_service(db: Session = Depends(get_db)) -> CatalogService:
    return CatalogService(db)


def get_elder_service(db: Session = Depends(get_db)) -> ElderService:
    return ElderService(db, ElderRepository(db))


def get_payment_service(
    db: Session = Depends(get_db),
    gateway: OnlinePaymentGateway = Depends(get_online_gateway),
) -> PaymentService:
    return PaymentService(db, gateway)


def get_order_service(
    db: Session = Depends(get_db),
    payments: PaymentService = Depends(get_payment_service),
    notifier: NotificationService = Depends(get_notification_service),
    audit: AuditService = Depends(get_audit_service),
    elders: ElderService = Depends(get_elder_service),
    catalog: CatalogService = Depends(get_catalog_service),
) -> OrderService:
    return OrderService(db, OrderRepository(db), payments, notifier, audit, elders, catalog)


def get_station_service(db: Session = Depends(get_db)) -> StationService:
    return StationService(db)


def get_staff_service(db: Session = Depends(get_db)) -> StaffService:
    return StaffService(db)


def get_supplier_service(db: Session = Depends(get_db)) -> SupplierService:
    return SupplierService(db)


def get_admin_service(
    db: Session = Depends(get_db),
    audit: AuditService = Depends(get_audit_service),
) -> AdminService:
    return AdminService(db, OrderRepository(db), audit)


def get_file_service(
    db: Session = Depends(get_db),
    storage: FileStorage = Depends(get_storage),
    local: FileStorage = Depends(get_local_storage),
) -> FileService:
    return FileService(db, storage, fallback=local)
