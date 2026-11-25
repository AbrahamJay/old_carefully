"""组织资源：服务区域、员工、供给方。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ...core.config import settings
from ...core.enums import Role, StaffStatus, UserStatus
from ...core.errors import BadRequestError, NotFoundError
from ...db.models import StaffProfile, Station, Supplier, User
from .schemas import (
    StaffCreate,
    StaffOut,
    StaffUpdate,
    StationCreate,
    StationUpdate,
    SupplierCreate,
)


class StationService:
    def __init__(self, db: Session) -> None:
        self._db = db

    def list_active(self) -> list[Station]:
        return list(
            self._db.scalars(
                select(Station).where(Station.active.is_(True)).order_by(Station.id)
            ).all()
        )

    def list_all(self) -> list[Station]:
        return list(self._db.scalars(select(Station).order_by(Station.id)).all())

    def get(self, station_id: int) -> Station:
        station = self._db.get(Station, station_id)
        if station is None:
            raise NotFoundError("区域不存在")
        return station

    def create(self, payload: StationCreate) -> Station:
        name = payload.name.strip()
        if self._db.scalars(select(Station).where(Station.name == name)).first():
            raise BadRequestError("区域名称已存在")
        station = Station(
            name=name,
            street=payload.street.strip(),
            address=payload.address.strip(),
            active=payload.active,
        )
        self._db.add(station)
        self._db.commit()
        self._db.refresh(station)
        return station

    def update(self, station_id: int, payload: StationUpdate) -> Station:
        station = self.get(station_id)
        updates = payload.model_dump(exclude_unset=True)
        if updates.get("name") is not None:
            updates["name"] = updates["name"].strip()
        for field, value in updates.items():
            setattr(station, field, value)
        self._db.commit()
        self._db.refresh(station)
        return station


class StaffService:
    def __init__(self, db: Session) -> None:
        self._db = db

    def list(self, station_id: int | None = None) -> list[StaffOut]:
        stmt = (
            select(User)
            .options(selectinload(User.station))
            .where(User.role == Role.STAFF)
            .order_by(User.id)
        )
        if station_id:
            stmt = stmt.where(User.station_id == station_id)
        return [self.to_out(user) for user in self._db.scalars(stmt).all()]

    def create(self, payload: StaffCreate) -> StaffOut:
        if self._db.scalars(select(User).where(User.phone == payload.phone)).first():
            raise BadRequestError("手机号已存在")

        station_id = payload.station_id or settings.default_station_id
        station = self._db.get(Station, station_id)
        if station is None:
            raise BadRequestError("服务区域不存在")

        user = User(
            name=payload.name,
            phone=payload.phone,
            role=Role.STAFF,
            status=UserStatus.ACTIVE,
            station_id=station_id,
        )
        self._db.add(user)
        self._db.flush()
        self._db.add(
            StaffProfile(
                user_id=user.id,
                supplier_id=payload.supplier_id,
                skills=payload.skills,
                status=StaffStatus.ACTIVE,
            )
        )
        self._db.commit()
        self._db.refresh(user)
        return StaffOut(
            id=user.id,
            name=user.name,
            phone=user.phone,
            role=user.role,
            skills=payload.skills,
            rating=5.0,
            status=StaffStatus.ACTIVE,
            station_id=station_id,
            station_name=station.name,
        )

    def update(self, staff_id: int, payload: StaffUpdate) -> StaffOut:
        user = self._db.get(User, staff_id)
        if user is None or user.role != Role.STAFF:
            raise NotFoundError("员工不存在")

        profile = self._db.get(StaffProfile, staff_id)
        if profile is None:
            profile = StaffProfile(user_id=staff_id, skills=[], status=StaffStatus.ACTIVE)
            self._db.add(profile)

        if payload.name is not None:
            user.name = payload.name
        if payload.skills is not None:
            profile.skills = payload.skills
        if payload.status is not None:
            profile.status = payload.status
            user.status = (
                UserStatus.ACTIVE if payload.status == StaffStatus.ACTIVE else UserStatus.DISABLED
            )
        if payload.supplier_id is not None:
            profile.supplier_id = payload.supplier_id
        if payload.station_id is not None:
            if self._db.get(Station, payload.station_id) is None:
                raise BadRequestError("服务区域不存在")
            user.station_id = payload.station_id

        self._db.commit()
        self._db.refresh(user)
        return self.to_out(user)

    def to_out(self, user: User) -> StaffOut:
        profile = self._db.get(StaffProfile, user.id)
        return StaffOut(
            id=user.id,
            name=user.name,
            phone=user.phone,
            role=user.role,
            skills=profile.skills if profile else [],
            rating=profile.rating if profile else 5.0,
            status=profile.status if profile else user.status,
            station_id=user.station_id,
            station_name=user.station.name if user.station else "",
        )


class SupplierService:
    def __init__(self, db: Session) -> None:
        self._db = db

    def list(self) -> list[Supplier]:
        return list(self._db.scalars(select(Supplier).order_by(Supplier.id)).all())

    def create(self, payload: SupplierCreate) -> Supplier:
        supplier = Supplier(**payload.model_dump())
        self._db.add(supplier)
        self._db.commit()
        self._db.refresh(supplier)
        return supplier

    def update(self, supplier_id: int, payload: SupplierCreate) -> Supplier:
        supplier = self._db.get(Supplier, supplier_id)
        if supplier is None:
            raise NotFoundError("供给方不存在")
        for field, value in payload.model_dump().items():
            setattr(supplier, field, value)
        self._db.commit()
        self._db.refresh(supplier)
        return supplier
