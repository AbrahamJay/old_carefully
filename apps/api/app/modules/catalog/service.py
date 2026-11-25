from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...core.errors import BadRequestError, NotFoundError
from ...db.models import Service
from .schemas import ServiceCreate


class CatalogService:
    def __init__(self, db: Session) -> None:
        self._db = db

    def list_active(self) -> list[Service]:
        return list(
            self._db.scalars(
                select(Service).where(Service.active.is_(True)).order_by(Service.sort, Service.id)
            ).all()
        )

    def list_all(self) -> list[Service]:
        return list(self._db.scalars(select(Service).order_by(Service.sort, Service.id)).all())

    def get(self, service_id: int) -> Service:
        service = self._db.get(Service, service_id)
        if service is None:
            raise NotFoundError("服务不存在")
        return service

    def get_bookable(self, service_id: int) -> Service:
        service = self._db.get(Service, service_id)
        if service is None or not service.active:
            raise NotFoundError("服务不存在或已下架")
        return service

    def create(self, payload: ServiceCreate) -> Service:
        if self._db.scalars(select(Service).where(Service.code == payload.code)).first():
            raise BadRequestError("服务编码已存在")
        service = Service(**payload.model_dump())
        self._db.add(service)
        self._db.commit()
        self._db.refresh(service)
        return service

    def update(self, service_id: int, payload: ServiceCreate) -> Service:
        service = self.get(service_id)
        for field, value in payload.model_dump().items():
            setattr(service, field, value)
        self._db.commit()
        self._db.refresh(service)
        return service
