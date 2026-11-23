"""Activity writes (data_model `activity_log` + `activity_recipients`). Rows join the caller's transaction.
Recipients are registered users only; unregistered placeholders have no feed.

`effects` maps a recipient to the change in their balance caused by the event, as integer minor units per currency
(`{user_id: {currency: amount_minor}}`, positive = gets back); zero entries are dropped before storing."""
import uuid
from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import notify
from app.models import ActivityLog, ActivityRecipient, User


def _effect_lines(by_currency: Mapping[str, int] | None) -> list[dict[str, Any]] | None:
    if not by_currency:
        return None
    lines = [{"currency": c, "amount_minor": v} for c, v in sorted(by_currency.items()) if v != 0]
    return lines or None


def record(db: Session, actor_id: uuid.UUID | None, action: str, entity_type: str, entity_id: uuid.UUID,
           group_id: uuid.UUID | None, payload: dict[str, Any], recipient_ids: Iterable[uuid.UUID],
           effects: Mapping[uuid.UUID, Mapping[str, int]] | None = None) -> ActivityLog:
    ids = set(recipient_ids)
    prefs: dict[uuid.UUID, Mapping[str, Any]] = {}
    if ids:
        prefs = {uid: p for uid, p in db.execute(
            select(User.id, User.notification_prefs).where(User.id.in_(ids), User.is_registered.is_(True),
                                                           User.deleted_at.is_(None)))}
        ids = set(prefs)
    row = ActivityLog(id=uuid.uuid4(), actor_id=actor_id, action=action, entity_type=entity_type,
                      entity_id=entity_id, group_id=group_id, payload=payload, created_at=datetime.now(timezone.utc))
    db.add(row)
    db.flush()
    db.add_all(ActivityRecipient(activity_id=row.id, user_id=uid,
                                 balance_effect=_effect_lines((effects or {}).get(uid)))
               for uid in sorted(ids, key=str))
    notify.fan_out(db, row, prefs)  # push rows for everyone but the actor, per their notification_prefs (S6-B-3)
    return row
