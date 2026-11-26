from __future__ import annotations

from datetime import date

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
    StaffLeaveCreate,
    StaffLeaveDeleteOut,
    StaffLeaveOut,
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


# --------------------------------------------------------------------- 请假
@router.get("/admin/staff/{staff_id}/leaves", response_model=list[StaffLeaveOut])
def admin_list_staff_leaves(
    staff_id: int,
    from_date: date | None = Query(default=None),
    to_date: date | None = Query(default=None),
    _: User = Depends(require_roles(Role.ADMIN)),
    service: StaffService = Depends(get_staff_service),
) -> list[StaffLeaveOut]:
    return [
        StaffLeaveOut.model_validate(item)
        for item in service.list_leaves(staff_id, from_date=from_date, to_date=to_date)
    ]


@router.post(
    "/admin/staff/{staff_id}/leaves", response_model=list[StaffLeaveOut], status_code=201
)
def admin_add_staff_leaves(
    staff_id: int,
    payload: StaffLeaveCreate,
    _: User = Depends(require_roles(Role.ADMIN)),
    service: StaffService = Depends(get_staff_service),
) -> list[StaffLeaveOut]:
    """按日期区间请假：区间内每天一条，已存在的当天记录只更新备注。"""
    return [
        StaffLeaveOut.model_validate(item)
        for item in service.add_leaves(staff_id, payload)
    ]


@router.delete("/admin/staff/{staff_id}/leaves", response_model=StaffLeaveDeleteOut)
def admin_delete_staff_leaves(
    staff_id: int,
    from_date: date = Query(...),
    to_date: date | None = Query(default=None),
    _: User = Depends(require_roles(Role.ADMIN)),
    service: StaffService = Depends(get_staff_service),
) -> StaffLeaveDeleteOut:
    """按日期区间整段删除请假记录。"""
    deleted = service.delete_leaves(staff_id, from_date=from_date, to_date=to_date)
    return StaffLeaveDeleteOut(deleted=deleted)


@router.delete("/admin/staff/{staff_id}/leaves/{leave_id}", status_code=204)
def admin_delete_staff_leave(
    staff_id: int,
    leave_id: int,
    _: User = Depends(require_roles(Role.ADMIN)),
    service: StaffService = Depends(get_staff_service),
) -> None:
    service.delete_leave(staff_id, leave_id)


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
