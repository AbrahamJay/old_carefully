from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ...core.enums import BindingStatus
from ...db.models import Elder, FamilyBinding, Station, User
from ...domain.authz import elder_visible_ids_stmt


class ElderRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def get(self, elder_id: int) -> Elder | None:
        return self._db.get(Elder, elder_id)

    def list_visible(self, user: User) -> list[Elder]:
        stmt = select(Elder).options(selectinload(Elder.station)).order_by(Elder.id.desc())
        visible_ids = elder_visible_ids_stmt(user)
        if visible_ids is not None:
            stmt = stmt.where(Elder.id.in_(visible_ids))
        return list(self._db.scalars(stmt).all())

    def list_by_station(self, station_id: int | None) -> list[Elder]:
        stmt = select(Elder).options(selectinload(Elder.station)).order_by(Elder.id.desc())
        if station_id:
            stmt = stmt.where(Elder.station_id == station_id)
        return list(self._db.scalars(stmt).all())

    def get_station(self, station_id: int) -> Station | None:
        return self._db.get(Station, station_id)

    def invite_code_taken(self, code: str) -> bool:
        return (
            self._db.scalars(select(Elder.id).where(Elder.invite_code == code)).first() is not None
        )

    def find_by_invite_code(self, code: str) -> Elder | None:
        return self._db.scalars(select(Elder).where(Elder.invite_code == code)).first()

    def binding_of(self, user_id: int, elder_id: int) -> FamilyBinding | None:
        return self._db.scalars(
            select(FamilyBinding).where(
                FamilyBinding.user_id == user_id,
                FamilyBinding.elder_id == elder_id,
            )
        ).first()

    def list_bindings(self, user_id: int) -> list[FamilyBinding]:
        return list(
            self._db.scalars(
                select(FamilyBinding)
                .options(selectinload(FamilyBinding.elder).selectinload(Elder.station))
                .where(
                    FamilyBinding.user_id == user_id,
                    FamilyBinding.status == BindingStatus.ACTIVE,
                )
                .order_by(FamilyBinding.id.desc())
            ).all()
        )

    def get_binding(self, binding_id: int) -> FamilyBinding | None:
        return self._db.get(FamilyBinding, binding_id)
