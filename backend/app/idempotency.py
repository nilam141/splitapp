"""Idempotency-Key support (data_model `idempotency_keys`). A repeat with the same key and user returns the stored
response (same status and body) for 24 hours; the same key on a different endpoint is 422 VALIDATION_ERROR."""
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import Request
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.errors import ApiError
from app.models import IdempotencyKey

TTL = timedelta(hours=24)


def parse_header(request: Request) -> uuid.UUID | None:
    raw = request.headers.get("Idempotency-Key")
    if raw is None:
        return None
    try:
        return uuid.UUID(raw.strip())
    except ValueError:
        raise ApiError(422, "VALIDATION_ERROR", "Idempotency-Key must be a UUID",
                       {"fields": [{"field": "Idempotency-Key", "message": "must be a UUID"}]})


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def lookup(db: Session, user_id: uuid.UUID, key: uuid.UUID, method_path: str) -> tuple[int, dict[str, Any]] | None:
    """Stored (status, body) for a live key, else None. A key used on another endpoint is a 422."""
    row = db.get(IdempotencyKey, (user_id, key))
    if row is None:
        return None
    if datetime.now(timezone.utc) - _aware(row.created_at) > TTL:
        db.execute(delete(IdempotencyKey).where(IdempotencyKey.user_id == user_id, IdempotencyKey.key == key))
        db.commit()
        return None
    if row.method_path != method_path:
        raise ApiError(422, "VALIDATION_ERROR", "Idempotency-Key was already used on a different endpoint",
                       {"fields": [{"field": "Idempotency-Key", "message": "already used on another endpoint"}]})
    return row.response_status, row.response_body


def store(db: Session, user_id: uuid.UUID, key: uuid.UUID, method_path: str, status: int,
          body: dict[str, Any]) -> None:
    """Add the key row to the caller's open transaction (committed together with the work it protects)."""
    db.add(IdempotencyKey(user_id=user_id, key=key, method_path=method_path, response_status=status,
                          response_body=body))


def is_duplicate_key_error(exc: IntegrityError) -> bool:
    return "idempotency_keys" in str(exc.orig)
