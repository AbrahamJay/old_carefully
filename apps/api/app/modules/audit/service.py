from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...db.models import AuditLog


class AuditService:
    """关键操作的留痕。写入方只需调用 ``record``，不必关心落库细节。"""

    def __init__(self, db: Session) -> None:
        self._db = db

    def record(
        self,
        actor_id: int | None,
        action: str,
        entity: str,
        entity_id: int | None,
        payload: dict | None = None,
    ) -> AuditLog:
        entry = AuditLog(
            actor_id=actor_id,
            action=action,
            entity=entity,
            entity_id=entity_id,
            payload=payload or {},
        )
        self._db.add(entry)
        return entry

    def list_recent(self, limit: int = 100) -> list[AuditLog]:
        return list(
            self._db.scalars(select(AuditLog).order_by(AuditLog.id.desc()).limit(limit)).all()
        )
