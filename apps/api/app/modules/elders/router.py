from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ...api.deps import get_current_user, get_elder_service, require_roles
from ...api.schemas import OkOut
from ...core.enums import Role
from ...db.models import Elder, User
from .schemas import (
    BindingCreate,
    BindingOut,
    BindingWithElderOut,
    ConsentCreate,
    ConsentOut,
    ElderCreate,
    ElderOut,
    ElderUpdate,
    InviteCodeOut,
)
from .service import ElderService

router = APIRouter(tags=["老人档案"])


def _to_out(elder: Elder, viewer: User) -> ElderOut:
    item = ElderOut.model_validate(elder)
    # 员工不应看到可用于绑定家属关系的邀请码
    if viewer.role == Role.STAFF:
        item.invite_code = None
    return item


@router.get("/elders", response_model=list[ElderOut])
def list_elders(
    user: User = Depends(get_current_user),
    service: ElderService = Depends(get_elder_service),
) -> list[ElderOut]:
    return [_to_out(elder, user) for elder in service.list_visible(user)]


@router.post("/elders", response_model=ElderOut, status_code=201)
def create_elder(
    payload: ElderCreate,
    user: User = Depends(require_roles(Role.CUSTOMER, Role.ADMIN)),
    service: ElderService = Depends(get_elder_service),
) -> ElderOut:
    return _to_out(service.create(user, payload), user)


@router.get("/elders/{elder_id}", response_model=ElderOut)
def get_elder(
    elder_id: int,
    user: User = Depends(get_current_user),
    service: ElderService = Depends(get_elder_service),
) -> ElderOut:
    return _to_out(service.get_accessible(user, elder_id), user)


@router.patch("/elders/{elder_id}", response_model=ElderOut)
def update_elder(
    elder_id: int,
    payload: ElderUpdate,
    user: User = Depends(require_roles(Role.CUSTOMER, Role.ADMIN)),
    service: ElderService = Depends(get_elder_service),
) -> ElderOut:
    return _to_out(service.update(user, elder_id, payload), user)


@router.post("/elders/{elder_id}/invite-code", response_model=InviteCodeOut)
def generate_invite_code(
    elder_id: int,
    user: User = Depends(require_roles(Role.CUSTOMER, Role.ADMIN)),
    service: ElderService = Depends(get_elder_service),
) -> InviteCodeOut:
    code = service.rotate_invite_code(user, elder_id)
    return InviteCodeOut(invite_code=code, elder_id=elder_id)


@router.post("/elders/{elder_id}/consents", response_model=ConsentOut, status_code=201)
def create_consent(
    elder_id: int,
    payload: ConsentCreate,
    user: User = Depends(require_roles(Role.CUSTOMER, Role.ADMIN)),
    service: ElderService = Depends(get_elder_service),
) -> ConsentOut:
    consent = service.add_consent(user, elder_id, payload)
    return ConsentOut(
        id=consent.id,
        elder_id=consent.elder_id,
        type=consent.type,
        version=consent.version,
        signed_at=consent.signed_at,
    )


@router.post("/bindings", response_model=BindingOut, status_code=201)
def bind_elder(
    payload: BindingCreate,
    user: User = Depends(require_roles(Role.CUSTOMER)),
    service: ElderService = Depends(get_elder_service),
) -> BindingOut:
    return BindingOut.model_validate(service.bind(user, payload))


@router.get("/bindings", response_model=list[BindingWithElderOut])
def list_bindings(
    user: User = Depends(require_roles(Role.CUSTOMER)),
    service: ElderService = Depends(get_elder_service),
) -> list[BindingWithElderOut]:
    result: list[BindingWithElderOut] = []
    for binding in service.list_bindings(user):
        item = BindingWithElderOut.model_validate(binding)
        item.elder = _to_out(binding.elder, user) if binding.elder else None
        result.append(item)
    return result


@router.delete("/bindings/{binding_id}", response_model=OkOut)
def unbind_elder(
    binding_id: int,
    user: User = Depends(require_roles(Role.CUSTOMER)),
    service: ElderService = Depends(get_elder_service),
) -> OkOut:
    service.unbind(user, binding_id)
    return OkOut()


@router.get("/admin/elders", response_model=list[ElderOut])
def admin_elders(
    station_id: int | None = Query(default=None),
    user: User = Depends(require_roles(Role.ADMIN)),
    service: ElderService = Depends(get_elder_service),
) -> list[ElderOut]:
    return [_to_out(elder, user) for elder in service.list_for_admin(station_id)]
