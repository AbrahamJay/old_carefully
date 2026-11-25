from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...core.errors import NotFoundError
from ...core.time import utcnow
from ...db.models import Notification


class NotificationService:
    """通知写入与读取。

    当前实现只落库（notification_provider=db）；
    接入微信订阅消息时在这里增加一个 channel 即可，不影响调用方。
    """

    def __init__(self, db: Session) -> None:
        self._db = db

    def notify(
        self,
        user_id: int,
        ntype: str,
        title: str,
        body: str,
        payload: dict | None = None,
    ) -> Notification:
        item = Notification(
            user_id=user_id,
            type=ntype,
            title=title,
            body=body,
            payload=payload or {},
        )
        self._db.add(item)
        return item

    def list_for(self, user_id: int, limit: int = 50) -> list[Notification]:
        return list(
            self._db.scalars(
                select(Notification)
                .where(Notification.user_id == user_id)
                .order_by(Notification.id.desc())
                .limit(limit)
            ).all()
        )

    def mark_read(self, user_id: int, notification_id: int) -> Notification:
        item = self._db.get(Notification, notification_id)
        if item is None or item.user_id != user_id:
            raise NotFoundError("通知不存在")
        item.read_at = utcnow()
        self._db.commit()
        return item
