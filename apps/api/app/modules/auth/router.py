from __future__ import annotations

from fastapi import APIRouter, Depends

from ...api.deps import get_auth_service, get_current_user
from ...core.security import create_access_token
from ...db.models import User
from .schemas import AdminLoginIn, LoginIn, TokenOut, UserOut, WechatLoginIn
from .service import AuthService

router = APIRouter(tags=["认证"])


def _token(user: User) -> TokenOut:
    return TokenOut(
        access_token=create_access_token(user.id, user.role),
        user=UserOut.model_validate(user),
    )


@router.post("/auth/login", response_model=TokenOut)
def login(payload: LoginIn, service: AuthService = Depends(get_auth_service)) -> TokenOut:
    return _token(service.login_by_password(payload.phone, payload.password))


@router.post("/auth/wechat", response_model=TokenOut)
def wechat_login(
    payload: WechatLoginIn,
    service: AuthService = Depends(get_auth_service),
) -> TokenOut:
    return _token(service.login_by_wechat(payload.code, payload.mock_openid))


@router.post("/auth/admin/login", response_model=TokenOut)
def admin_login(
    payload: AdminLoginIn,
    service: AuthService = Depends(get_auth_service),
) -> TokenOut:
    return _token(service.login_admin(payload.username, payload.password))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> UserOut:
    return UserOut.model_validate(user)
