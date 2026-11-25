from __future__ import annotations

from fastapi import APIRouter, Depends

from ...api.deps import get_admin_service, require_roles
from ...core.enums import Role
from ...db.models import User
from .schemas import AdminReviewOut, AuditLogOut, StatsOut
from .service import AdminService

router = APIRouter(tags=["运营后台"])


@router.get("/admin/stats", response_model=StatsOut)
def admin_stats(
    _: User = Depends(require_roles(Role.ADMIN)),
    service: AdminService = Depends(get_admin_service),
) -> StatsOut:
    return service.stats()


@router.get("/admin/reviews", response_model=list[AdminReviewOut])
def admin_reviews(
    _: User = Depends(require_roles(Role.ADMIN)),
    service: AdminService = Depends(get_admin_service),
) -> list[AdminReviewOut]:
    return service.reviews()


@router.get("/admin/audit-logs", response_model=list[AuditLogOut])
def admin_audit_logs(
    _: User = Depends(require_roles(Role.ADMIN)),
    service: AdminService = Depends(get_admin_service),
) -> list[AuditLogOut]:
    return [AuditLogOut.model_validate(item) for item in service.audit_logs()]
