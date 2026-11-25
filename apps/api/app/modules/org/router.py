from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ...api.deps import (
    get_current_user,
    get_staff_service,
    get_station_service,
    get_supplier_service,
    require_roles,
)
from ...core.enums import Role
from ...db.models import User
from .schemas import (
    StaffCreate,
    StaffOut,
    StaffUpdate,
    StationCreate,
    StationOut,
    StationUpdate,
    SupplierCreate,
    SupplierOut,
)
from .service import StaffService, StationService, SupplierService

router = APIRouter(tags=["组织资源"])


# --------------------------------------------------------------------- 区域
@router.get("/stations", response_model=list[StationOut])
def list_stations(
    _: User = Depends(get_current_user),
    service: StationService = Depends(get_station_service),
) -> list[StationOut]:
    return [StationOut.model_validate(item) for item in service.list_active()]


@router.get("/admin/stations", response_model=list[StationOut])
def admin_list_stations(
    _: User = Depends(require_roles(Role.ADMIN)),
    service: StationService = Depends(get_station_service),
) -> list[StationOut]:
    return [StationOut.model_validate(item) for item in service.list_all()]


@router.post("/admin/stations", response_model=StationOut, status_code=201)
def admin_create_station(
    payload: StationCreate,
    _: User = Depends(require_roles(Role.ADMIN)),
    service: StationService = Depends(get_station_service),
) -> StationOut:
    return StationOut.model_validate(service.create(payload))


@router.patch("/admin/stations/{station_id}", response_model=StationOut)
def admin_update_station(
    station_id: int,
    payload: StationUpdate,
    _: User = Depends(require_roles(Role.ADMIN)),
    service: StationService = Depends(get_station_service),
) -> StationOut:
    return StationOut.model_validate(service.update(station_id, payload))


# --------------------------------------------------------------------- 员工
@router.get("/admin/staff", response_model=list[StaffOut])
def admin_list_staff(
    station_id: int | None = Query(default=None),
    _: User = Depends(require_roles(Role.ADMIN)),
    service: StaffService = Depends(get_staff_service),
) -> list[StaffOut]:
    return service.list(station_id)


@router.post("/admin/staff", response_model=StaffOut, status_code=201)
def admin_create_staff(
    payload: StaffCreate,
    _: User = Depends(require_roles(Role.ADMIN)),
    service: StaffService = Depends(get_staff_service),
) -> StaffOut:
    return service.create(payload)


@router.patch("/admin/staff/{staff_id}", response_model=StaffOut)
def admin_update_staff(
    staff_id: int,
    payload: StaffUpdate,
    _: User = Depends(require_roles(Role.ADMIN)),
    service: StaffService = Depends(get_staff_service),
) -> StaffOut:
    return service.update(staff_id, payload)


# ------------------------------------------------------------------- 供给方
@router.get("/admin/suppliers", response_model=list[SupplierOut])
def admin_list_suppliers(
    _: User = Depends(require_roles(Role.ADMIN)),
    service: SupplierService = Depends(get_supplier_service),
) -> list[SupplierOut]:
    return [SupplierOut.model_validate(item) for item in service.list()]


@router.post("/admin/suppliers", response_model=SupplierOut, status_code=201)
def admin_create_supplier(
    payload: SupplierCreate,
    _: User = Depends(require_roles(Role.ADMIN)),
    service: SupplierService = Depends(get_supplier_service),
) -> SupplierOut:
    return SupplierOut.model_validate(service.create(payload))


@router.patch("/admin/suppliers/{supplier_id}", response_model=SupplierOut)
def admin_update_supplier(
    supplier_id: int,
    payload: SupplierCreate,
    _: User = Depends(require_roles(Role.ADMIN)),
    service: SupplierService = Depends(get_supplier_service),
) -> SupplierOut:
    return SupplierOut.model_validate(service.update(supplier_id, payload))
