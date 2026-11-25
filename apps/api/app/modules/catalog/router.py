from __future__ import annotations

from fastapi import APIRouter, Depends

from ...api.deps import get_catalog_service, require_roles
from ...core.enums import Role
from ...db.models import User
from .schemas import ServiceCreate, ServiceOut
from .service import CatalogService

router = APIRouter(tags=["服务目录"])


@router.get("/services", response_model=list[ServiceOut])
def list_services(service: CatalogService = Depends(get_catalog_service)) -> list[ServiceOut]:
    return [ServiceOut.model_validate(item) for item in service.list_active()]


@router.get("/admin/services", response_model=list[ServiceOut])
def admin_list_services(
    _: User = Depends(require_roles(Role.ADMIN)),
    service: CatalogService = Depends(get_catalog_service),
) -> list[ServiceOut]:
    return [ServiceOut.model_validate(item) for item in service.list_all()]


@router.post("/admin/services", response_model=ServiceOut, status_code=201)
def admin_create_service(
    payload: ServiceCreate,
    _: User = Depends(require_roles(Role.ADMIN)),
    service: CatalogService = Depends(get_catalog_service),
) -> ServiceOut:
    return ServiceOut.model_validate(service.create(payload))


@router.patch("/admin/services/{service_id}", response_model=ServiceOut)
def admin_update_service(
    service_id: int,
    payload: ServiceCreate,
    _: User = Depends(require_roles(Role.ADMIN)),
    service: CatalogService = Depends(get_catalog_service),
) -> ServiceOut:
    return ServiceOut.model_validate(service.update(service_id, payload))
