"""Opaque keyset cursors. A cursor is url-safe base64 of a JSON list `[date | null, created_at, id]`; anything else
is rejected as a malformed cursor (422 VALIDATION_ERROR, field `cursor`)."""
import base64
import binascii
import json
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone

from app.errors import ApiError


@dataclass(frozen=True)
class Key:
    """Position of the last item returned: the (date, created_at, id) sort key. `day` is None for comments."""

    day: date | None
    created_at: datetime
    id: uuid.UUID


def aware(dt: datetime) -> datetime:
    """Always UTC: naive datetimes come from SQLite test databases (stored as UTC), and PostgreSQL returns timestamps
    in the connection's zone, so responses and cursors are normalised to one representation."""
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def bad_cursor() -> ApiError:
    return ApiError(422, "VALIDATION_ERROR", "Invalid cursor",
                    {"fields": [{"field": "cursor", "message": "Not a valid cursor"}]})


def encode(key: Key) -> str:
    raw = json.dumps([key.day.isoformat() if key.day else None, aware(key.created_at).isoformat(), str(key.id)],
                     separators=(",", ":"))
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def decode(cursor: str, *, dated: bool) -> Key:
    try:
        if len(cursor) > 200:
            raise ValueError("too long")
        data = json.loads(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)))
        if not isinstance(data, list):
            raise ValueError("not a list")
        day, created, ident = data  # must be exactly three items
        if (day is None) == dated:
            raise ValueError("date part does not match the list kind")
        created_at = datetime.fromisoformat(created)
        if created_at.tzinfo is None:
            raise ValueError("created_at needs a zone")
        return Key(date.fromisoformat(day) if dated else None, created_at.astimezone(timezone.utc),
                   uuid.UUID(ident))
    except (ValueError, TypeError, binascii.Error, UnicodeDecodeError):
        raise bad_cursor()
