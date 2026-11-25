from __future__ import annotations

import uuid

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ...core.config import settings
from ...core.enums import Role, UserStatus
from ...core.errors import (
    BadRequestError,
    ForbiddenError,
    UnauthorizedError,
)
from ...core.security import verify_password
from ...db.models import Station, User


class AuthService:
    def __init__(self, db: Session) -> None:
        self._db = db

    def login_by_password(self, phone: str, password: str) -> User:
        """手机号 + 密码登录。"""
        user = self._db.scalars(select(User).where(User.phone == phone)).first()
        if user is None or not verify_password(password, user.password_hash):
            # 账号不存在与密码错误给同一提示，避免手机号被枚举
            raise UnauthorizedError("手机号或密码错误")
        if user.status != UserStatus.ACTIVE:
            raise ForbiddenError("账号不可用")
        return user

    def login_by_wechat(self, code: str, mock_openid: str | None) -> User:
        if not settings.allow_demo_login:
            raise BadRequestError("微信登录尚未配置，请先接入 code2session", http_status=501)
        openid = mock_openid or f"mock-{code or uuid.uuid4().hex[:8]}"
        user = self._db.scalars(select(User).where(User.openid == openid)).first()
        if user is None:
            user = User(
                openid=openid,
                name="微信用户",
                role=Role.CUSTOMER,
                status=UserStatus.ACTIVE,
                station_id=self._default_station_id(),
            )
            self._db.add(user)
            self._db.commit()
            self._db.refresh(user)
        return user

    def _default_station_id(self) -> int | None:
        """默认站点存在才归属。

        空库（``AUTO_SEED=false``）里站点表可能为空，此时写死 id 会撞外键，
        而自注册客户本来就不必须有归属站点。
        """
        station_id = settings.default_station_id
        if station_id and self._db.get(Station, station_id) is not None:
            return station_id
        return None

    def login_admin(self, username: str, password: str) -> User:
        user = self._db.scalars(
            select(User).where(
                or_(User.phone == username, User.name == username),
                User.role == Role.ADMIN,
            )
        ).first()
        if user is None or not verify_password(password, user.password_hash):
            raise UnauthorizedError("账号或密码错误")
        return user