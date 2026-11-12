"""Notification outbox. Rows are written in the caller's transaction; delivery is a console/log sender until the
real sender ships (S6-B-3). The log line omits the payload in production because reset payloads hold secrets."""
import logging
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.config import PRODUCTION_ENVS, settings
from app.models import Notification

log = logging.getLogger("app.outbox")


def enqueue(db: Session, user_id: uuid.UUID, type_: str, channel: str, payload: dict[str, Any]) -> Notification:
    row = Notification(user_id=user_id, type=type_, channel=channel, payload=payload, status="pending", attempts=0)
    db.add(row)
    if settings.env.lower() in PRODUCTION_ENVS:
        log.info("outbox %s/%s queued for user %s", channel, type_, user_id)
    else:
        log.info("outbox %s/%s queued for user %s: %s", channel, type_, user_id, payload)
    return row
