from __future__ import annotations

from sqlalchemy.orm import Session

from ...core.config import settings
from ...core.enums import BindingStatus, Role
from ...core.errors import BadRequestError, ConflictError, ForbiddenError, NotFoundError
from ...core.ids import new_invite_code
from ...db.models import Consent, Elder, FamilyBinding, User
from ...domain.authz import can_access_elder
from .repository import ElderRepository
from .schemas import BindingCreate, ConsentCreate, ElderCreate, ElderUpdate


class ElderService:
    def __init__(self, db: Session, repo: ElderRepository) -> None:
        self._db = db
        self._repo = repo

    # ------------------------------------------------------------------ 查询
    def list_visible(self, user: User) -> list[Elder]:
        return self._repo.list_visible(user)

    def list_for_admin(self, station_id: int | None) -> list[Elder]:
        return self._repo.list_by_station(station_id)

    def get_accessible(
        self, user: User, elder_id: int, *, forbidden_message: str | None = None
    ) -> Elder:
        elder = self._repo.get(elder_id)
        if elder is None:
            raise NotFoundError("老人档案不存在")
        if not can_access_elder(self._db, user, elder_id):
            raise ForbiddenError(forbidden_message)
        return elder

    # ------------------------------------------------------------------ 写入
    def create(self, user: User, payload: ElderCreate) -> Elder:
        station_id = payload.station_id or settings.default_station_id
        station = self._repo.get_station(station_id)
        if station is None or not station.active:
            raise BadRequestError("服务区域不存在或已停用")

        elder = Elder(
            station_id=station_id,
            name=payload.name,
            gender=payload.gender,
            birth_year=payload.birth_year,
            phone=payload.phone,
            address=payload.address,
            community=payload.community,
            health_notes=payload.health_notes,
            emergency_name=payload.emergency_name,
            emergency_phone=payload.emergency_phone,
            invite_code=self._new_unique_invite_code(),
            created_by=user.id,
        )
        self._db.add(elder)
        self._db.flush()
        if user.role == Role.CUSTOMER:
            self._db.add(
                FamilyBinding(
                    user_id=user.id,
                    elder_id=elder.id,
                    relation="self",
                    status=BindingStatus.ACTIVE,
                )
            )
        self._db.commit()
        self._db.refresh(elder)
        return elder

    def update(self, user: User, elder_id: int, payload: ElderUpdate) -> Elder:
        elder = self.get_accessible(user, elder_id)
        updates = payload.model_dump(exclude_unset=True)

        new_station_id = updates.get("station_id")
        if new_station_id is not None and new_station_id != elder.station_id:
            station = self._repo.get_station(new_station_id)
            if station is None or not station.active:
                raise BadRequestError("服务区域不存在或已停用")

        for field, value in updates.items():
            setattr(elder, field, value)
        self._db.commit()
        self._db.refresh(elder)
        return elder

    def rotate_invite_code(self, user: User, elder_id: int) -> str:
        elder = self.get_accessible(user, elder_id)
        elder.invite_code = self._new_unique_invite_code()
        self._db.commit()
        return elder.invite_code or ""

    def add_consent(self, user: User, elder_id: int, payload: ConsentCreate) -> Consent:
        self.get_accessible(user, elder_id)
        consent = Consent(
            elder_id=elder_id,
            type=payload.type,
            version=payload.version,
            signed_by=payload.signed_by or user.name,
        )
        self._db.add(consent)
        self._db.commit()
        self._db.refresh(consent)
        return consent

    # ------------------------------------------------------------------ 绑定
    def bind(self, user: User, payload: BindingCreate) -> FamilyBinding:
        elder = self._repo.find_by_invite_code(payload.invite_code.strip().upper())
        if elder is None:
            raise NotFoundError("邀请码无效")

        binding = self._repo.binding_of(user.id, elder.id)
        if binding is not None:
            binding.status = BindingStatus.ACTIVE
            binding.relation = payload.relation
        else:
            binding = FamilyBinding(
                user_id=user.id,
                elder_id=elder.id,
                relation=payload.relation,
                status=BindingStatus.ACTIVE,
            )
            self._db.add(binding)
        self._db.commit()
        self._db.refresh(binding)
        return binding

    def list_bindings(self, user: User) -> list[FamilyBinding]:
        return self._repo.list_bindings(user.id)

    def unbind(self, user: User, binding_id: int) -> None:
        binding = self._repo.get_binding(binding_id)
        if binding is None or binding.user_id != user.id:
            raise NotFoundError("绑定不存在")
        binding.status = BindingStatus.REVOKED
        self._db.commit()

    # ------------------------------------------------------------------ 内部
    def _new_unique_invite_code(self) -> str:
        for _ in range(20):
            code = new_invite_code()
            if not self._repo.invite_code_taken(code):
                return code
        raise ConflictError("邀请码生成失败，请重试")
