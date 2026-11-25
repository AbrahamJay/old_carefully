from __future__ import annotations

from fastapi import APIRouter, Depends

from ...api.deps import get_current_user, get_notification_service
from ...api.schemas import OkOut
from ...db.models import User
from .schemas import NotificationOut
from .service import NotificationService

router = APIRouter(tags=["通知"])


@router.get("/notifications", response_model=list[NotificationOut])
def list_notifications(
    user: User = Depends(get_current_user),
    service: NotificationService = Depends(get_notification_service),
) -> list[NotificationOut]:
    return [NotificationOut.model_validate(item) for item in service.list_for(user.id)]


@router.post("/notifications/{notification_id}/read", response_model=OkOut)
def read_notification(
    notification_id: int,
    user: User = Depends(get_current_user),
    service: NotificationService = Depends(get_notification_service),
) -> OkOut:
    service.mark_read(user.id, notification_id)
    return OkOut()
