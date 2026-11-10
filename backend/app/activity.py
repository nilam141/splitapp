"""Activity writes (data_model `activity_log` + `activity_recipients`). Rows join the caller's transaction.
Recipients are registered users only; unregistered placeholders have no feed."""
import uuid
from collections.abc import Iterable
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ActivityLog, ActivityRecipient, User


def record(db: Session, actor_id: uuid.UUID | None, action: str, entity_type: str, entity_id: uuid.UUID,
           group_id: uuid.UUID | None, payload: dict[str, Any], recipient_ids: Iterable[uuid.UUID]) -> ActivityLog:
    ids = set(recipient_ids)
    if ids:
        ids = set(db.scalars(select(User.id).where(User.id.in_(ids), User.is_registered.is_(True),
                                                   User.deleted_at.is_(None))))
    row = ActivityLog(id=uuid.uuid4(), actor_id=actor_id, action=action, entity_type=entity_type,
                      entity_id=entity_id, group_id=group_id, payload=payload)
    db.add(row)
    db.flush()
    db.add_all(ActivityRecipient(activity_id=row.id, user_id=uid) for uid in sorted(ids, key=str))
    return row
